# Financeiro Familiar - App Web (MVP v1)

Aplicação web para uso contínuo, sem precisar editar/deployar HTML a cada atualização.

## O que este MVP já faz

- Upload de `Base_Consolidada_Financas_Familia.csv` pela interface
- Persistência em banco SQLite (`finance_app/finance.db`)
- Deduplicação por `id_lancamento_sistema` (ou hash fallback)
- Dashboard com KPIs, filtros e tabela de lançamentos
- Conciliação `Cartão x Conta` (baseada em categoria `Pagamento Fatura Cartao`)

## Rodar local

```bash
cd finance_app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

Abra:

- http://localhost:8080

## Fluxo de uso

1. Clique em `Importar base consolidada (CSV)`
2. Selecione `../Base_Consolidada_Financas_Familia.csv`
3. Clique em `Importar`
4. Use filtros normalmente

## Deploy único mais rápido (Render)

Use o `render.yaml` já pronto nesta pasta.

1. Suba esta pasta para um repositório GitHub.
2. No Render, clique em `New +` -> `Blueprint`.
3. Conecte o repositório e confirme o deploy.
4. O serviço sobe com:
   - URL fixa
   - disco persistente em `/var/data`
   - banco SQLite em `/var/data/finance.db`
5. Abra a URL, faça upload do CSV e use normalmente.

Depois disso, você não precisa mais redeployar para atualizar lançamentos: basta usar o upload no próprio app.

### Observação prática

Se quiser escala maior depois, migramos de SQLite para PostgreSQL sem quebrar o front.

## Próximo passo recomendado

- Integrar parser direto de PDFs/prints no upload (sem precisar passar pela base CSV manual).
