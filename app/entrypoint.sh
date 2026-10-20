#!/bin/bash
set -e

echo "[Entrypoint] Détection automatique d'Ollama..."

# Adresses possibles pour Ollama : OLLAMA_HOST (configuration explicite) est testé en premier
OLLAMA_CANDIDATES=(
    "${OLLAMA_HOST}"              # Variable d'environnement personnalisée
    "host.docker.internal:11434"  # Mac/Windows avec Docker Desktop
    "localhost:11434"              # Mode host sur Linux
    "172.17.0.1:11434"            # Bridge gateway (si Ollama écoute sur 0.0.0.0)
)

# Fonction pour tester la connexion à Ollama
test_ollama() {
    local host=$1
    if [ -z "$host" ]; then
        return 1
    fi

    echo "[Entrypoint] Test de connexion à Ollama sur http://$host ..."
    if timeout 2 curl -sf "http://$host/api/tags" > /dev/null 2>&1; then
        echo "[Entrypoint] ✓ Ollama détecté sur http://$host"
        return 0
    fi
    return 1
}

# Tester chaque candidat
OLLAMA_DETECTED=""
TESTED=" "
for candidate in "${OLLAMA_CANDIDATES[@]}"; do
    case "$TESTED" in *" $candidate "*) continue ;; esac  # déjà testé (doublon)
    TESTED="$TESTED$candidate "
    if test_ollama "$candidate"; then
        OLLAMA_DETECTED="$candidate"
        break
    fi
done

if [ -n "$OLLAMA_DETECTED" ]; then
    export OLLAMA_HOST="$OLLAMA_DETECTED"
    echo "[Entrypoint] Configuration automatique: OLLAMA_HOST=$OLLAMA_HOST"
else
    echo "[Entrypoint] ⚠️  Ollama non détecté automatiquement"
    echo "[Entrypoint] Utilisation de la configuration par défaut: ${OLLAMA_HOST:-host.docker.internal:11434}"
    export OLLAMA_HOST="${OLLAMA_HOST:-host.docker.internal:11434}"
fi

# Lancer l'application
echo "[Entrypoint] Démarrage de l'application..."
exec "$@"
