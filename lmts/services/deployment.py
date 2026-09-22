from __future__ import annotations

from dataclasses import dataclass

from lmts.tools.output import FilePayload, OutputTarget, write_files
from lmts.tools.web_deploy import php_package_files


@dataclass(frozen=True, slots=True)
class ServerDeployConfig:
    host: str
    database: str
    username: str
    password: str
    publish_key: str

    def __post_init__(self) -> None:
        for label, value in (
            ('host', self.host),
            ('database', self.database),
            ('username', self.username),
            ('password', self.password),
            ('publish_key', self.publish_key),
        ):
            if not str(value).strip():
                raise ValueError(f'server database {label} must not be empty')


def _php_single_quoted(value: str) -> str:
    return value.replace('\\', '\\\\').replace("'", "\\'")


def render_server_db_php(config: ServerDeployConfig) -> str:
    host = _php_single_quoted(config.host)
    database = _php_single_quoted(config.database)
    username = _php_single_quoted(config.username)
    password = _php_single_quoted(config.password)
    publish_key = _php_single_quoted(config.publish_key)
    return (
        "<?php\n\n"
        "return [\n"
        f"    'dsn' => 'mysql:host={host};dbname={database};charset=utf8mb4',\n"
        f"    'user' => '{username}',\n"
        f"    'password' => '{password}',\n"
        f"    'publish_key' => '{publish_key}',\n"
        "];\n"
    )


class DeploymentPackageBuilder:
    def build(self, config: ServerDeployConfig) -> dict[str, FilePayload]:
        files: dict[str, FilePayload] = dict(php_package_files())
        files['config.php'] = render_server_db_php(config)
        return files


def deploy_server(
    target: OutputTarget,
    config: ServerDeployConfig,
    *,
    builder: DeploymentPackageBuilder | None = None,
) -> list[str]:
    package_builder = builder or DeploymentPackageBuilder()
    return write_files(target, package_builder.build(config))
