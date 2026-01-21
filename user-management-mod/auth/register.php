<?php
require "../utils/user_functions.php";

$name = $_POST['name'];
$email = $_POST['email'];
$password = password_hash($_POST['password'], PASSWORD_DEFAULT);

$users = loadUsers();

$users[] = [
  "id" => count($users) + 1,
  "name" => $name,
  "email" => $email,
  "password" => $password,
  "role" => "Job Getter",
  "status" => "active"
];

saveUsers($users);
echo "Registration successful";
