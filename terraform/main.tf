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
# NACL
# --------------------

resource "aws_network_acl" "public_nacl" {
  vpc_id     = aws_vpc.vpc.id
  subnet_ids = [aws_subnet.publicSubnet.id]

  tags = merge(var.tags, { Name = "public-nacl-allow-all" })
}

# --------------------
# INBOUND: 80 tcp, 3389
# --------------------

# HTTP (80)
resource "aws_network_acl_rule" "in_http" {
  network_acl_id = aws_network_acl.public_nacl.id
  rule_number    = 100
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 80
  to_port        = 80
}

# RDP (3389)
resource "aws_network_acl_rule" "in_rdp" {
  network_acl_id = aws_network_acl.public_nacl.id
  rule_number    = 110
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 3389
  to_port        = 3389
}

# Rückverkehr (Ephemeral Ports)
resource "aws_network_acl_rule" "in_ephemeral" {
  network_acl_id = aws_network_acl.public_nacl.id
  rule_number    = 120
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 1024
  to_port        = 65535
}


# --------------------
# OUTBOUND: ALLES ERLAUBT
# --------------------
resource "aws_network_acl_rule" "public_out_all_ipv4" {
  network_acl_id = aws_network_acl.public_nacl.id
  rule_number    = 100
  egress         = true
  protocol       = "-1"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
}

resource "aws_network_acl_rule" "public_out_all_ipv6" {
  network_acl_id  = aws_network_acl.public_nacl.id
  rule_number     = 110
  egress          = true
  protocol        = "-1"  
  rule_action     = "allow"
  ipv6_cidr_block = "::/0"
}

# --------------------
# VPC
# --------------------
resource "aws_vpc" "vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, {
    Name = "vpc" 
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
    Name = "igw"
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
  name        = "ec2-sg"
  description = "Allow HTTP (80) and RDP (3389)"
  vpc_id      = aws_vpc.vpc.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "RDP"
    from_port   = 3389
    to_port     = 3389
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "ec2-sg" })
}


resource "aws_security_group" "rds_sg" {
  name        = "rds-sg"
  description = "Allow MariaDB from EC2 SG only"
  vpc_id      = aws_vpc.vpc.id

  ingress {
    description     = "MariaDB from EC2"
    from_port       = 3306
    to_port         = 3306
    protocol        = "tcp"
    security_groups = [aws_security_group.ec2_sg.id] # NUR EC2-Instanzen, die diese Security Group haben, dürfen zur DB verbinden
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "rds-sg"
  })
}

# --------------------
# DB Subnet Group
# --------------------
resource "aws_db_subnet_group" "db_snet_group" {
  name = "db-subnet-group"

  subnet_ids = [
    aws_subnet.privateSubnet.id,
    aws_subnet.privateSubnet2.id
  ]

  tags = merge(var.tags, {
    Name = "db-subnet-group"
  })
}

# --------------------
# RDS MariaDB
# --------------------
resource "aws_db_instance" "db_instance" {
  identifier        = "mariadb"
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
    Name = "mariadb"
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
    Name = "ec2"
  })
}
