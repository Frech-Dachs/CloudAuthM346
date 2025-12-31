output "db_endpoint" {
  description = "RDS endpoint hostname"
  value       = aws_db_instance.db_instance.address
}

output "db_port" {
  description = "RDS port"
  value       = aws_db_instance.db_instance.port
}

output "ec2_public_ip" {
  description = "EC2 public IP (for SSH)"
  value       = aws_instance.instance.public_ip
}

output "ec2_private_ip" {
  description = "EC2 private IP (inside the VPC)"
  value       = aws_instance.instance.private_ip
}
