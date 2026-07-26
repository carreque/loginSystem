output "authorizer_role_arn" {
    value = aws_iam_role.authorizer.arn
}

output "get_resource_role_arn"    { 
    value = aws_iam_role.get_resource.arn 
}
output "create_resource_role_arn" { 
    value = aws_iam_role.create_resource.arn 
}
output "create_user_role_arn"     { 
    value = aws_iam_role.create_user.arn
}