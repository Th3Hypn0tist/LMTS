# LMTS deploy

## Local PHP

The local PHP deploy keeps the two LMTS web surfaces separate:

- Reporting: `php/` -> `/home/www/lmts-report/`
- Benchmark: `php/visualizer/` -> `/home/www/lmts/`

Reporting excludes `visualizer/` and preserves the host-owned
`/home/www/lmts-report/config.php`.

The benchmark API uses the host-owned shared config at
`/home/www/config.php`.

Run:

```bash
bash deploy/local-php.sh reporting
bash deploy/local-php.sh benchmark
bash deploy/local-php.sh all
```

Paths can be overridden with:

- `LMTS_LOCAL_REPORT_ROOT`
- `LMTS_LOCAL_BENCHMARK_ROOT`
- `LMTS_LOCAL_SHARED_CONFIG`

The deploy performs PHP syntax checks before copying and keeps the deployed
tree owned by `root:www-data` with directory mode 755 and file mode 644.
