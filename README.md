# LLM Observability Lab
demo - 


## Demarrage (important : toujours builder avec --build)

```bash
# Premier demarrage OU apres modification de l'app
docker compose up -d --build

# Verifier que les metriques arrivent (attendre ~15s)
curl http://localhost:8000/metrics | grep "^llm_"

# Acces
open http://localhost:3000       # Grafana (admin/admin) - dashboard auto-importe
open http://localhost:8000/docs  # API FastAPI
open http://localhost:8428       # VictoriaMetrics UI
```

Si `curl /metrics` retourne 22 bytes ("Not Found") :
```bash
docker compose down
docker compose up -d --build --force-recreate
```

Pour inclure Phoenix (traces LLM + eval) :
```bash
docker compose --profile phoenix up -d --build
open http://localhost:6006
```

## Declencher les derives en demo

```bash
chmod +x scripts/drift.sh

./scripts/drift.sh concept 0.8    # eval score chute  -> alerte Grafana
./scripts/drift.sh pipeline 0.7   # TTFT > 3s         -> heatmap s'emballe
./scripts/drift.sh data 0.6       # token spike        -> data drift visible
./scripts/drift.sh all 0.5        # les 3 simultanement
./scripts/drift.sh inject          # simulation injection
./scripts/drift.sh reset           # retour baseline
./scripts/drift.sh status          # etat actuel
```

## Architecture metriques

```
llm-app:8000/metrics  <-- VictoriaMetrics scrape toutes les 5s --> Grafana
```

Pas d'intermediaire OTLP pour les metriques. Scrape direct, fiable.

## Metriques exposees

| Metrique | Type | Description |
|----------|------|-------------|
| llm_ttft_seconds | Histogram | Time To First Token |
| llm_input_tokens_total | Counter | Tokens input par modele |
| llm_output_tokens_total | Counter | Tokens output par modele |
| llm_cost_usd_total | Counter | Cout cumule USD |
| llm_errors_total | Counter | Erreurs par type |
| llm_requests_total | Counter | Requetes par statut |
| llm_eval_score | Gauge | Score qualite 0-1 |
| llm_rag_score | Gauge | Score retrieval RAG |
| llm_rag_latency_seconds | Histogram | Latence RAG |
| llm_prompt_chars | Histogram | Longueur prompt |
| llm_drift_active | Gauge | Derive active (0/1) |

## Requetes MetricsQL cles

```promql
histogram_quantile(0.99, rate(llm_ttft_seconds_bucket[2m]))
avg(llm_eval_score)
rate(llm_input_tokens_total[1m]) * 60
rate(llm_cost_usd_total[2m]) / rate(llm_input_tokens_total[2m])
```

## Demo scenarisee (recommande pour le meetup)

```bash
chmod +x scripts/demo.sh

./scripts/demo.sh full      # sequence complete ~5 min avec pauses
./scripts/demo.sh concept   # concept drift seul (3 min)
./scripts/demo.sh pipeline  # pipeline drift seul (3 min)
./scripts/demo.sh status    # metriques actuelles dans le terminal
```

## Nouvelles metriques

| Metrique | Description |
|----------|-------------|
| llm_hallucination_rate | Taux d hallucinations par modele - le KPI business du Concept Drift |
| llm_user_satisfaction | Score /5 derive de eval_score et TTFT - langage business |
| llm_active_sessions | Sessions en cours - realisme du trafic |
| llm_drift_active | Intensite de la derive active (0=off, 0-1=intensite) |
