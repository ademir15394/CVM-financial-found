import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
import zipfile
import tempfile
import boto3

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'cvm_ingestion_control')
# O bucket S3 deve conter apenas o nome limpo, sem o protocolo 's3://'
S3_BUCKET = os.environ.get('S3_BUCKET_NAME', 'cvm-landing-zone-dev-404438143202')

table = dynamodb.Table(TABLE_NAME)

# Mapeamento dos datasets e padrões de URL da CVM (formato anual consolidado)
DATASETS_CONFIG = {
    'INFORME_MENSAL_CADASTRAL': {
        'url_pattern': 'https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_{ano}.zip',
        's3_prefix': 'cvm_data/inf-cad/'
    }
}

def get_competence_record(dataset_type: str, ano_mes: str) -> dict:
    """Obtém o registro da competência (ano_mes) no DynamoDB."""
    try:
        response = table.get_item(Key={
            'dataset_type': dataset_type,
            'ano_mes': ano_mes
        })
        return response.get('Item')
    except Exception as e:
        print(f"Erro ao buscar no DynamoDB ({dataset_type} {ano_mes}): {str(e)}")
        return None

def save_competence_record(dataset_type: str, ano_mes: str, url: str, etag: str, last_modified: str, status: str, s3_location: str = None, is_representation: bool = False):
    """Atualiza a competência no DynamoDB considerando histórico e reapresentação."""
    now_iso = datetime.now(timezone.utc).isoformat()
    
    existing = get_competence_record(dataset_type, ano_mes)
    version_count = (existing.get('version_count', 1) + 1) if (existing and is_representation) else 1

    item = {
        'dataset_type': dataset_type,
        'ano_mes': ano_mes,
        'file_name': url.split("/")[-1],
        'url': url,
        'etag': etag or 'N/A',
        'last_modified': last_modified or 'N/A',
        'status_leitura': status,
        'ultima_atualizacao': now_iso,
        'version_count': version_count
    }
    
    if s3_location:
        item['s3_location'] = s3_location

    try:
        table.put_item(Item=item)
        print(f"[{dataset_type}] Mês {ano_mes} salvo com status '{status}' (Versão: {version_count}).")
    except Exception as e:
        print(f"Erro ao salvar no DynamoDB: {str(e)}")

def process_month_competence(dataset_type: str, ref_date: datetime, s3_bucket: str):
    """
    Processa um mês de competência específico para um determinado dataset.
    """
    config = DATASETS_CONFIG[dataset_type]
    ano_str = ref_date.strftime("%Y")           # Ex: 2026 (para o arquivo anual da CVM)
    ano_mes_key = ref_date.strftime("%Y-%m")    # Ex: 2026-10 (para controle no DynamoDB e pastas)
    
    url = config['url_pattern'].format(ano=ano_str)
    file_name = url.split("/")[-1]

    # 1. Obter metadados HTTP do arquivo na CVM via HEAD request
    req = urllib.request.Request(url, method='HEAD')
    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
    
    try:
        with urllib.request.urlopen(req) as response:
            headers = response.info()
            remote_etag = headers.get('ETag', '').strip('"')
            remote_last_modified = headers.get('Last-Modified', '')
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"[{dataset_type}] Arquivo anual para o ano {ano_str} ainda não disponibilizado pela CVM (404).")
        else:
            print(f"Erro HTTP {e.code} ao acessar {url}")
        return
    except Exception as e:
        print(f"Erro ao acessar {url}: {str(e)}")
        return

    # 2. Verificar estado prévio no DynamoDB para esse mês/competência
    existing_record = get_competence_record(dataset_type, ano_mes_key)
    
    if existing_record:
        local_etag = existing_record.get('etag')
        
        # Se o ETag for igual ao que já gravamos, o arquivo não sofreu alterações
        if remote_etag and local_etag == remote_etag:
            print(f"[{dataset_type}] Mês {ano_mes_key} sem alterações (ETag idêntico). Ignorando download.")
            save_competence_record(
                dataset_type=dataset_type,
                ano_mes=ano_mes_key,
                url=url,
                etag=remote_etag,
                last_modified=remote_last_modified,
                status='SKIPPED_UNCHANGED',
                s3_location=existing_record.get('s3_location')
            )
            return
        else:
            print(f"[{dataset_type}] ATENÇÃO: Detectada REAPRESENTAÇÃO de dados no mês {ano_mes_key}! Baixando e descompactando nova versão...")
            is_representation = True
    else:
        is_representation = False

    # 3. Utilizar diretório temporário isolado para download e descompactação
    s3_prefix = config['s3_prefix']
    
    get_req = urllib.request.Request(url, method='GET')
    get_req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
    
    try:
        # O bloco TemporaryDirectory garante a limpeza automática ao sair do 'with'
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_zip_path = os.path.join(temp_dir, file_name)
            
            # Baixar o ZIP diretamente para o diretório temporário
            print(f"[{dataset_type}] Baixando {file_name} para o diretório temporário...")
            with urllib.request.urlopen(get_req) as response, open(temp_zip_path, 'wb') as out_file:
                out_file.write(response.read())
                
            # Descompactar o ficheiro ZIP dentro do mesmo diretório temporário
            extracted_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extracted_dir, exist_ok=True)
            
            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                zip_ref.extractall(extracted_dir)
                print(f"[{dataset_type}] Ficheiro descompactado com sucesso na pasta temporária.")

            # Percorrer e enviar cada ficheiro extraído (ex: CSVs) para o S3
            last_s3_location = None
            for root, dirs, files in os.walk(extracted_dir):
                for file in files:
                    local_file_path = os.path.join(root, file)
                    # Mantém a estrutura de pastas organizada por ano e mês na Landing Zone
                    s3_key = f"{s3_prefix}ano={ref_date.year}/mes={ref_date.strftime('%m')}/{file}"
                    
                    print(f"[{dataset_type}] Enviando {file} para s3://{s3_bucket}/{s3_key}")
                    s3_client.upload_file(local_file_path, s3_bucket, s3_key)
                    last_s3_location = f"s3://{s3_bucket}/{s3_key}"
            
        status_final = 'REPRESENTED_DOWNLOADED' if is_representation else 'DOWNLOADED'
        
        save_competence_record(
            dataset_type=dataset_type,
            ano_mes=ano_mes_key,
            url=url,
            etag=remote_etag,
            last_modified=remote_last_modified,
            status=status_final,
            s3_location=last_s3_location,
            is_representation=is_representation
        )
        print(f"[{dataset_type}] Processo concluído para o mês {ano_mes_key}.")

    except Exception as e:
        print(f"Falha no processamento do mês {ano_mes_key}: {str(e)}")

def lambda_handler(event, context):
    """
    Executa a raspagem para a janela de meses desejada.
    Exemplo: Mês atual + últimos 3 meses (para pegar reapresentações retroativas).
    """
    months_window = event.get('months_window', 3)
    current_date = datetime.now()
    
    # Gera a lista das últimas N competências (mês/ano)
    dates_to_check = [current_date - relativedelta(months=i) for i in range(months_window)]
    
    for dataset_type in DATASETS_CONFIG.keys():
        for ref_date in dates_to_check:
            process_month_competence(dataset_type, ref_date, S3_BUCKET)
            
    return {
        'statusCode': 200,
        'body': f'Processamento concluído para a janela dos últimos {months_window} meses.'
    }