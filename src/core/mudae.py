"""Comando do Mudae que adiciona as imagens enviadas a uma custom."""

# Limite de caracteres de uma mensagem do Discord (sem Nitro)
DISCORD_MESSAGE_LIMIT = 2000


def mudae_command(title, links):
    """Comando do Mudae que adiciona as imagens à custom `title`."""
    return f"$ai {title} $\n" + " $\n".join(links)


def mudae_commands(title, links, limit=DISCORD_MESSAGE_LIMIT):
    """Comando dividido em mensagens que cabem no limite do Discord.

    Com ~40 imagens o comando único passava de 2000 caracteres e o Discord
    recusava a mensagem. Cada parte é um $ai completo para a mesma custom.
    """
    parts, current = [], []
    for link in links:
        candidate = current + [link]
        if current and len(mudae_command(title, candidate)) > limit:
            parts.append(mudae_command(title, current))
            candidate = [link]
        current = candidate
    if current:
        parts.append(mudae_command(title, current))
    return parts
