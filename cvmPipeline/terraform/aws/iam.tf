# ==========================================
# 1. IAM ROLE E POLICIES PARA AS LAMBDAS
# ==========================================

# Confiança (Trust Policy) para o serviço Lambda assumir a role
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec_role" {
  name               = "cvm_lambda_execution_role_${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

# Permissões operacionais da Lambda (CloudWatch Logs, S3 Landing Zone e DynamoDB)
data "aws_iam_policy_document" "lambda_permissions" {
  statement {
    sid       = "CloudWatchLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:*:*:*"]
  }

  statement {
    sid       = "S3LandingZoneAccess"
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
    resources = [
      aws_s3_bucket.landing_zone.arn,
      "${aws_s3_bucket.landing_zone.arn}/*"
    ]
  }

  statement {
    sid       = "DynamoDBControlAccess"
    effect    = "Allow"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.ingestion_control.arn]
  }
}

resource "aws_iam_policy" "lambda_policy" {
  name        = "cvm_lambda_policy_${var.environment}"
  description = "Politica de acesso ao S3, DynamoDB e Logs para as funcoes Lambda da CVM"
  policy      = data.aws_iam_policy_document.lambda_permissions.json
}

resource "aws_iam_role_policy_attachment" "lambda_attach" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}


# ==========================================
# 2. IAM OIDC E ROLE PARA O GITHUB ACTIONS
# ==========================================

# Provedor OIDC do GitHub na AWS
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1", "1c58a21860c07ebb1530e38a2c20e501d51a0210"]
}

# Confiança para o GitHub Actions assumir a role via OIDC com segurança (sem chaves)
data "aws_iam_policy_document" "github_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:ref:refs/heads/main"]
    }
  }
}

data "aws_iam_policy_document" "github_actions_assume_role_policy" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [
        # Curinga inteligente que cobre tanto o formato tradicional quanto o novo formato 
        # com IDs imutáveis do GitHub para o seu repositório específico
        "repo:ademir15394*/*CVM-financial-found*:*"
      ]
    }
  }
}
resource "aws_iam_role" "github_actions_role" {
  name               = "cvm_github_actions_role_dev"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume_role_policy.json
}

# Anexo da política padrão do ECR para o pipeline do GitHub Actions fazer push das imagens
resource "aws_iam_role_policy_attachment" "github_ecr_attach" {
  role       = aws_iam_role.github_actions_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser"
}