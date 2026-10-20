terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# Configure the AWS Provider
provider "aws" {
  region = "us-east-1"
}


variable "environment" {
  description = "Ambiente de implantação"
  type        = string
  default     = "dev"
}

variable "github_repo" {
  description = "Repositório no GitHub no formato 'usuario/repo' para a Role do OIDC"
  type        = string
  default     = "seu-usuario-github/cvmpipeline"
}