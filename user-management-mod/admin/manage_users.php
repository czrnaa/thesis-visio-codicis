<?php
session_start();

// if user is logged in
if (!isset($_SESSION['user'])) {
  die("You must log in first!");
}

// if user is admin
if ($_SESSION['user']['role'] !== 'Admin') {
  die("Access denied");
}

// user is admin
echo "Welcome Admin! Here you can manage users.";
