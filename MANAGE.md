# 🔧 Guide de gestion — Family RAG

Référence rapide pour gérer, diagnostiquer et maintenir votre instance Family RAG.

---

## 📋 Informations du projet

| Élément | Valeur |
|---------|--------|
| Version | 2.6.0 |
| Service | `family-rag` |
| Container | `family-rag` |
| Volume | `family-rag-index` |
| Port | `8000` |
| URL | http://localhost:8000 |
| Ollama requis | 0.13.1+ |

---

## 🚀 Démarrage

```bash
# Premier lancement (build + start)
docker compose up -d --build

# Lancements suivants
docker compose up -d
```

---

## 🛑 Arrêt

```bash
# Arrêt simple (conserve l'index)
docker compose down

# Arrêt + suppression de l'index
docker compose down -v
```

---

## 🔍 Diagnostic

### Vérifier le statut

```bash
# État du container
docker compose ps

# Santé de l'application
curl -s http://localhost:8000/health | jq
```

### Voir les logs

```bash
# Logs en temps réel
docker compose logs -f

# Dernières 50 lignes
docker compose logs --tail 50

# Logs avec timestamp
docker compose logs -t
```

### Vérifier Ollama

```bash
# Ollama actif ?
curl -s http://localhost:11434/api/tags | jq

# Modèles installés
ollama list
```

### Vérifier les ressources

```bash
# Utilisation mémoire/CPU du container
docker stats family-rag --no-stream

# Espace disque du volume
docker system df -v | grep family-rag
```

---

## 🔧 Dépannage

### Le container ne démarre pas

```bash
# Voir les erreurs
docker compose logs

# Rebuild complet
docker compose down -v
docker compose up -d --build
```

### Ollama non connecté

```bash
# Vérifier qu'Ollama tourne
pgrep -x ollama || echo "Ollama non lancé"

# Lancer Ollama
ollama serve

# Tester la connexion depuis le container
docker exec family-rag curl -s http://host.docker.internal:11434/api/tags
```

### Erreur "model not found"

```bash
# Lister les modèles disponibles
ollama list

# Installer un modèle manquant
ollama pull mistral:latest
ollama pull nomic-embed-text
```

### Réponses lentes

```bash
# Vérifier la RAM allouée à Docker Desktop
# Recommandé : minimum 8 GB

# Utiliser un modèle plus léger
ollama pull phi3:mini
```

### Documents non détectés

```bash
# Vérifier le contenu du dossier RAG
ls -la ./RAG/

# Vérifier le montage dans le container
docker exec family-rag ls -la /data/

# Permissions
chmod -R 755 ./RAG/
```

### OCR ne fonctionne pas

```bash
# Vérifier que Tesseract est installé dans le container
docker exec family-rag tesseract --version

# Vérifier les langues disponibles
docker exec family-rag tesseract --list-langs
```

### Vision ne fonctionne pas

```bash
# Vérifier la version Ollama (0.13.1+ requis)
ollama --version

# Vérifier que Ministral 3 est installé
ollama list | grep ministral

# Installer Ministral 3 si absent
ollama pull ministral-3:latest

# Tester la vision manuellement
curl http://localhost:11434/api/chat -d '{
  "model": "ministral-3:latest",
  "messages": [{"role": "user", "content": "test"}]
}'
```

### Réinitialiser l'index

```bash
# Supprimer uniquement le volume d'index
docker compose down
docker volume rm family-rag-index
docker compose up -d
```

---

## 🧹 Nettoyage

### Nettoyage léger (conserve l'image)

```bash
docker compose down -v
```

### Nettoyage complet

```bash
# Tout supprimer (container + volume + image)
docker compose down -v --rmi local

# Vérifier
docker ps -a | grep family-rag
docker volume ls | grep family-rag
docker images | grep family-rag
```

### Nettoyage forcé (si erreurs)

```bash
# Supprimer manuellement
docker rm -f family-rag 2>/dev/null
docker volume rm family-rag-index 2>/dev/null
docker rmi familyrag-family-rag 2>/dev/null

# Nettoyer les ressources orphelines
docker system prune -f
```

---

## 💾 Sauvegarde

### Sauvegarder l'index vectoriel

```bash
# Créer un backup de l'index
docker run --rm \
  -v family-rag-index:/source:ro \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/index-$(date +%Y%m%d-%H%M%S).tar.gz -C /source .
```

### Sauvegarder les documents

```bash
# Simplement copier le dossier RAG
cp -r ./RAG ./backups/RAG-$(date +%Y%m%d-%H%M%S)
```

### Sauvegarde complète

```bash
#!/bin/bash
BACKUP_DIR="./backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Documents
cp -r ./RAG "$BACKUP_DIR/"

# Index
docker run --rm \
  -v family-rag-index:/source:ro \
  -v "$BACKUP_DIR":/backup \
  alpine tar czf /backup/index.tar.gz -C /source .

# Config
cp docker-compose.yml "$BACKUP_DIR/"

echo "Backup créé : $BACKUP_DIR"
```

### Restaurer l'index

```bash
# Arrêter le service
docker compose down

# Supprimer l'ancien volume
docker volume rm family-rag-index

# Créer et restaurer
docker volume create family-rag-index
docker run --rm \
  -v family-rag-index:/target \
  -v $(pwd)/backups:/backup:ro \
  alpine tar xzf /backup/index-XXXXXX.tar.gz -C /target

# Redémarrer
docker-compose up -d
```

---

## 🔄 Mise à jour

### Mettre à jour l'application

```bash
# Récupérer les nouveaux fichiers
git pull  # ou remplacer manuellement

# Rebuild
docker compose down
docker compose up -d --build
```

### Mettre à jour les modèles Ollama

```bash
# Mettre à jour un modèle
ollama pull mistral:latest

# L'application utilisera automatiquement la nouvelle version
```

---

## 📊 Commandes utiles

| Action | Commande |
|--------|----------|
| Statut | `docker compose ps` |
| Logs | `docker compose logs -f` |
| Shell dans le container | `docker exec -it family-rag /bin/bash` |
| Redémarrer | `docker compose restart` |
| Stats ressources | `docker stats family-rag` |
| Inspecter le volume | `docker volume inspect family-rag-index` |
| Tester l'API | `curl http://localhost:8000/health` |
| Lister les fichiers indexés | `curl http://localhost:8000/api/files` |
| Stats de l'index | `curl http://localhost:8000/api/stats` |
| Vérifier Tesseract | `docker exec family-rag tesseract --version` |

---

## 🌐 Accès réseau

Family RAG est **local par défaut** : le port 8000 n'est lié qu'à `127.0.0.1` (mode bridge, mappage `127.0.0.1:8000:8000`) et, avec `docker-compose.linux.yml`, l'application n'écoute que sur `127.0.0.1`.

> ⚠️ L'application n'a **pas d'authentification** et donne accès à tous vos documents indexés. Ne l'exposez pas au réseau local : changer le mappage de port ou l'adresse d'écoute n'est pas pris en charge. Un `docker run -p 8000:8000` hors compose l'exposerait sur toutes les interfaces (utilisez `-p 127.0.0.1:8000:8000`). Ollama doit lui aussi rester sur `127.0.0.1`, son réglage par défaut.
