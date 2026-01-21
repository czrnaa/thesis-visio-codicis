<?php
session_start();
require "../utils/user_functions.php";

$email = $_POST['email'];
$password = $_POST['password'];

$user = findUserByEmail($email);

if ($user && password_verify($password, $user['password'])) {
  $_SESSION['user'] = $user;
  echo "Login successful";
} else {
  echo "Invalid credentials";
}
