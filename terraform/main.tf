# --------------------
# Variables
# --------------------
variable "db_username" {
  description = "RDS master username"
  type        = string
  default     = "admin"
}

variable "db_password" {
  description = "RDS master password (use a strong password!)"
  type        = string
  sensitive   = true
  default     = "CloudAuth"
}

# --------------------
# VPC
# --------------------
resource "aws_vpc" "vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, {
    Name = "demo-vpc"
  })
}

# --------------------
# Subnets
# --------------------
resource "aws_subnet" "publicSubnet" {
  vpc_id                  = aws_vpc.vpc.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "us-east-1a"
  map_public_ip_on_launch = true

  tags = merge(var.tags, {
    Name = "public-subnet-1a"
  })
}

resource "aws_subnet" "privateSubnet" {
  vpc_id            = aws_vpc.vpc.id
  cidr_block        = "10.0.11.0/24"
  availability_zone = "us-east-1a"

  tags = merge(var.tags, {
    Name = "private-subnet-1a"
  })
}

resource "aws_subnet" "privateSubnet2" {
  vpc_id            = aws_vpc.vpc.id
  cidr_block        = "10.0.12.0/24"
  availability_zone = "us-east-1b"

  tags = merge(var.tags, {
    Name = "private-subnet-1b"
  })
}

# --------------------
# Internet Gateway
# --------------------
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.vpc.id

  tags = merge(var.tags, {
    Name = "demo-igw"
  })
}

# --------------------
# Route Table (PUBLIC)
# --------------------
resource "aws_route_table" "public_rt" {
  vpc_id = aws_vpc.vpc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = merge(var.tags, {
    Name = "public-rt"
  })
}

resource "aws_route_table_association" "public_assoc" {
  subnet_id      = aws_subnet.publicSubnet.id
  route_table_id = aws_route_table.public_rt.id
}

# --------------------
# Security Groups
# --------------------
resource "aws_security_group" "ec2_sg" {
  name        = "demo-ec2-sg"
  description = "Allow all inbound traffic to EC2"
  vpc_id      = aws_vpc.vpc.id

  ingress {
    description      = "All inbound (IPv4/IPv6)"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "demo-ec2-sg"
  })
}

resource "aws_security_group" "rds_sg" {
  name        = "demo-rds-sg"
  description = "Allow MariaDB from EC2 SG only"
  vpc_id      = aws_vpc.vpc.id

  ingress {
    description     = "MariaDB from EC2"
    from_port       = 3306
    to_port         = 3306
    protocol        = "tcp"
    security_groups = [aws_security_group.ec2_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "demo-rds-sg"
  })
}

# --------------------
# DB Subnet Group
# --------------------
resource "aws_db_subnet_group" "db_snet_group" {
  name = "demo-db-subnet-group"

  subnet_ids = [
    aws_subnet.privateSubnet.id,
    aws_subnet.privateSubnet2.id
  ]

  tags = merge(var.tags, {
    Name = "demo-db-subnet-group"
  })
}

# --------------------
# RDS MariaDB
# --------------------
resource "aws_db_instance" "db_instance" {
  identifier        = "demo-mariadb"
  engine            = "mariadb"
  instance_class    = "db.t3.medium"
  allocated_storage = 20
  storage_type      = "gp3"

  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.db_snet_group.name
  vpc_security_group_ids = [aws_security_group.rds_sg.id]

  publicly_accessible = false
  skip_final_snapshot = true
  deletion_protection = false

  tags = merge(var.tags, {
    Name = "demo-mariadb"
  })
}

# --------------------
# EC2 Instance
# --------------------
resource "aws_instance" "instance" {
  ami               = "ami-0b4bc1e90f30ca1ec"
  instance_type     = "t3.medium"
  subnet_id         = aws_subnet.publicSubnet.id
  availability_zone = "us-east-1a"

  vpc_security_group_ids = [aws_security_group.ec2_sg.id]

  key_name="vockey"

  tags = merge(var.tags, {
    Name = "demo-ec2"
  })
}
