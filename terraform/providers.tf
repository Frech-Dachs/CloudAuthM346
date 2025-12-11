terraform {
  required_providers {
    aws = {
      version = "= 5.100.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}
