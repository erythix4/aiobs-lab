#!/bin/sh
# Generateur de charge - continu
# Tourne en boucle independamment de l'app interne

URL="http://llm-app:8000"
MODELS="gpt-4o gpt-4o-mini llama-3 mistral"

PROMPTS="
Duree du conge paternite ?
Remboursement frais transport ?
Preavis en cas de demission ?
Horaires service client ?
Bulletin de salaire en ligne ?
Avantages salaries seniors ?
Modifier mon adresse dans le RH ?
Formations disponibles ce trimestre ?
Politique de teletravail ?
Declarer un arret maladie ?
Regles heures supplementaires ?
Plan epargne entreprise ?
"

i=0
while true; do
  i=$((i + 1))

  # Rotation modele
  M_IDX=$((i % 4 + 1))
  MODEL=$(echo "$MODELS" | tr ' ' '\n' | sed -n "${M_IDX}p")

  # Rotation prompt
  P_IDX=$(( (i * 3 + 7) % 12 + 1))
  PROMPT=$(echo "$PROMPTS" | grep -v '^$' | sed -n "${P_IDX}p")
  [ -z "$PROMPT" ] && PROMPT="Questions sur les conges ?"

  # RAG alterne
  USE_RAG="true"
  [ $((i % 4)) -eq 0 ] && USE_RAG="false"

  # Session pool
  SESSION="ext-$((i % 40))"

  curl -sf -X POST "$URL/query" \
    -H "Content-Type: application/json" \
    -d "{\"prompt\":\"$PROMPT\",\"model\":\"$MODEL\",\"use_rag\":$USE_RAG,\"session_id\":\"$SESSION\"}" \
    > /dev/null 2>&1

  sleep 1
done
