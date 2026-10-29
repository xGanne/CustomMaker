"""Tamanho das customs exportadas: formatação e limite de aviso."""


def format_bytes(n):
    """'148 KB', '2,3 MB' — vírgula decimal, como no resto do app (pt-BR)."""
    n = max(0, int(n or 0))
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{round(n / 1024):d} KB"
    return f"{n / (1024 * 1024):.1f} MB".replace(".", ",")


def warn_limit_bytes(app_config):
    """Limite de aviso em bytes, ou None quando o aviso está desligado (0)."""
    try:
        mb = float(app_config.get("export_size_warn_mb", 8.0) or 0)
    except (TypeError, ValueError, AttributeError):
        mb = 8.0
    return int(mb * 1024 * 1024) if mb > 0 else None


def size_summary(sizes):
    """Resumo de {path: bytes}: (total, (path_maior, bytes_maior) | None)."""
    if not sizes:
        return 0, None
    largest = max(sizes.items(), key=lambda item: item[1])
    return sum(sizes.values()), largest
