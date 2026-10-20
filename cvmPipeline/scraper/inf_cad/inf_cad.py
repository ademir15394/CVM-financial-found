import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
import boto3

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'cvm_ingestion_control')
S3_BUCKET = os.environ.get('S3_BUCKET_NAME', 's3://databricks-data-file-404438143202-us-east-1-an/')

table = dynamodb.Table(TABLE_NAME)

# Mapeamento dos datasets e padrões de URL da CVM
DATASETS_CONFIG = {
    'INFORME_DIARIO': {
        'url_pattern': 'https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_{ano_mes_str}.zip',
        's3_prefix': 'raw/cvm/informe_diario/'
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
        print(f"Erro ao buscar no DynamoDB ({dataset_type} - {ano_mes}): {str(e)}")
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
    ano_mes_str = ref_date.strftime("%Y%m")     # Ex: 202604
    ano_mes_key = ref_date.strftime("%Y-%m")    # Ex: 2026-04
    
    url = config['url_pattern'].format(ano_mes_str=ano_mes_str)
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
            print(f"[{dataset_type}] Arquivo para o mês {ano_mes_key} ainda não disponibilizado pela CVM (404).")
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
        
        # Se o ETag for igual ao que já gravamos, o arquivo não sofreu reapresentação
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
            print(f"[{dataset_type}] ATENÇÃO: Detectada REAPRESENTAÇÃO de dados no mês {ano_mes_key}! Baixando nova versão...")
            is_representation = True
    else:
        is_representation = False

    # 3. Baixar arquivo atualizado/novo e salvar no S3 organizando por competência
    s3_key = f"{config['s3_prefix']}ano={ref_date.year}/mes={ref_date.strftime('%m')}/{file_name}"
    
    get_req = urllib.request.Request(url, method='GET')
    get_req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
    
    try:
        with urllib.request.urlopen(get_req) as response:
            s3_client.upload_fileobj(
                Fileobj=response,
                Bucket=s3_bucket,
                Key=s3_key
            )
            
        s3_location = f"s3://{s3_bucket}/{s3_key}"
        status_final = 'REPRESENTED_DOWNLOADED' if is_representation else 'DOWNLOADED'
        
        save_competence_record(
            dataset_type=dataset_type,
            ano_mes=ano_mes_key,
            url=url,
            etag=remote_etag,
            last_modified=remote_last_modified,
            status=status_final,
            s3_location=s3_location,
            is_representation=is_representation
        )

    except Exception as e:
        print(f"Falha no download/upload do mês {ano_mes_key}: {str(e)}")

def lambda_handler(event, context):
    """
    Executa a raspagem para a janela de meses desejada.
    Exemplo: Mês atual + últimos 3 meses (para pegar reapresentações retroativas).
    """
    # Quantidade de meses retroativos a verificar por reapresentações
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