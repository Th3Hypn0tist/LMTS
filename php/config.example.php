<?php

// PHP uses PDO_MYSQL for MariaDB connections.
return [
    'dsn' => 'mysql:host=127.0.0.1;dbname=lmts;charset=utf8mb4',
    'user' => 'lmts',
    'password' => 'CHANGE_ME',
    // Optional. Must be a private directory outside the public web root.
    // When omitted, LMTS uses sys_get_temp_dir()/lmts-report-upload.
    'upload_staging_dir' => '/var/tmp/lmts-report-upload',
];
