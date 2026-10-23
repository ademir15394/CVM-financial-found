resource "aws_ecr_repository" "scrapers" {
  name                 = "cvm-scrapers"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Regra de retenção para guardar apenas as últimas 5 imagens e economizar armazenamento
resource "aws_ecr_lifecycle_policy" "scrapers_policy" {
  repository = aws_ecr_repository.scrapers.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Manter apenas as ultimas 5 imagens"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = {
        type = "expire"
      }
    }]
  })
}