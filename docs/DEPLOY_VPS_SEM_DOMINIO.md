# Deploy VPS sem dominio — modo temporario

Este roteiro coloca o sistema no ar por IP publico da VPS, sem dominio, sem HTTPS e sem restricao por IP da empresa.

Uso esperado:

```text
http://IP_PUBLICO_DA_VPS
```

> Este modo e adequado para homologacao ou uso controlado inicial. Para producao final, recomenda-se dominio, HTTPS e controle de acesso por IP/VPN/Zero Trust.

---

## 1. Entrar na VPS

```bash
ssh deploy@IP_DA_VPS
```

---

## 2. Preparar estrutura

```bash
sudo mkdir -p /opt/dfeb/estoque/{app,backups,logs,scripts}
sudo chown -R deploy:deploy /opt/dfeb
chmod 750 /opt/dfeb/estoque
```

---

## 3. Clonar o repositorio

```bash
cd /opt/dfeb/estoque
git clone -b fix/ajustes-alinhamento git@github.com:LucasGS520/Estoque-DFeB.git app
cd /opt/dfeb/estoque/app
```

Se a pasta ja existir:

```bash
cd /opt/dfeb/estoque/app
git fetch origin
git checkout fix/ajustes-alinhamento
git pull --ff-only origin fix/ajustes-alinhamento
```

---

## 4. Criar `.env`

```bash
cp .env.example .env
nano .env
```

Configure:

```env
APP_BASE_URL=http://IP_PUBLICO_DA_VPS
ADMIN_PASSWORD=SENHA_FORTE
```

Gerar senha forte:

```bash
openssl rand -base64 32
```

---

## 5. Preparar dados persistentes

```bash
mkdir -p data/uploads data/exports data/backups
sudo chown -R 1000:1000 data
```

---

## 6. Instalar dependencias de backup no host

```bash
sudo apt update
sudo apt install -y sqlite3
```

---

## 7. Subir a aplicacao

```bash
docker compose build --pull
docker compose up -d
```

Verificar:

```bash
docker compose ps
docker logs --tail=100 estoque-dfeb
docker logs --tail=100 nginx-dfeb
```

Acessar:

```text
http://IP_PUBLICO_DA_VPS
```

---

## 8. Permissoes dos scripts

```bash
chmod +x scripts/backup_sqlite.sh scripts/deploy_vps.sh
```

---

## 9. Testar backup

```bash
./scripts/backup_sqlite.sh
ls -lh /opt/dfeb/estoque/backups
```

---

## 10. Agendar backup diario

```bash
(crontab -l 2>/dev/null; echo "0 2 * * * cd /opt/dfeb/estoque/app && ./scripts/backup_sqlite.sh >> /opt/dfeb/estoque/logs/backup.log 2>&1") | crontab -
```

---

## 11. Atualizar o sistema depois

```bash
cd /opt/dfeb/estoque/app
./scripts/deploy_vps.sh
```

---

## 12. Portas esperadas

Apenas estas portas devem ficar publicas:

```text
22/tcp  SSH
80/tcp  HTTP via Nginx
```

A porta `8501` do Streamlit nao deve ser aberta publicamente. Ela fica disponivel apenas na rede Docker interna.
