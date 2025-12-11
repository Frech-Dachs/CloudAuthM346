resource "aws_vpc" "vpc" {
  tags       = merge(var.tags, {})
  cidr_block = "10.0.0.0/16"
}

resource "aws_subnet" "publicSubnet" {
  vpc_id                  = aws_vpc.vpc.id
  tags                    = merge(var.tags, {})
  map_public_ip_on_launch = true
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "us-east-1a"
}

resource "aws_subnet" "privateSubnet" {
  vpc_id            = aws_vpc.vpc.id
  tags              = merge(var.tags, {})
  cidr_block        = "10.0.11.0/24"
  availability_zone = "us-east-1a"
}

resource "aws_db_instance" "db_instance" {
  tags                 = merge(var.tags, {})
  instance_class       = "db.m7g.large"
  engine               = "mariadb"
  db_subnet_group_name = aws_db_subnet_group.db_snet_group.name
  availability_zone    = "us-east-1a"
  allocated_storage    = 20
  username             = "admin"
}

resource "aws_db_subnet_group" "db_snet_group" {
  tags = merge(var.tags, {})

  subnet_ids = [
    aws_subnet.privateSubnet.id,
    aws_subnet.privateSubnet2.id,
  ]
}

resource "aws_subnet" "privateSubnet2" {
  vpc_id            = aws_vpc.vpc.id
  tags              = merge(var.tags, {})
  cidr_block        = "10.0.12.0/24"
  availability_zone = "us-east-1b"
}

resource "aws_instance" "instance" {
  tags              = merge(var.tags, {})
  subnet_id         = aws_subnet.publicSubnet.id
  instance_type     = "t3.medium"
  availability_zone = "us-east-1a"
  ami               = "ami-0b4bc1e90f30ca1ec"
}

