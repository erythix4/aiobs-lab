#!/bin/sh
# trigger_drift.sh
# Usage: ./trigger_drift.sh [data|concept|pipeline|all|reset] [intensity 0.1-1.0]

URL="http://localhost:8000"
TYPE="${1:-reset}"
INTENSITY="${2:-0.7}"

case "$TYPE" in
  data|concept|pipeline|all)
    curl -sf -X POST "$URL/drift" \
      -H "Content-Type: application/json" \
      -d "{\"drift_type\":\"$TYPE\",\"intensity\":$INTENSITY}" | python3 -m json.tool
    ;;
  reset)
    curl -sf -X POST "$URL/drift" \
      -H "Content-Type: application/json" \
      -d '{"drift_type":"reset"}' | python3 -m json.tool
    ;;
  inject)
    curl -sf -X POST "$URL/inject" | python3 -m json.tool
    ;;
  error)
    ETYPE="${2:-timeout}"
    curl -sf -X POST "$URL/error/$ETYPE" | python3 -m json.tool
    ;;
  status)
    curl -sf "$URL/status" | python3 -m json.tool
    ;;
  *)
    echo "Usage: $0 [data|concept|pipeline|all|reset|inject|error <type>|status] [intensity]"
    echo ""
    echo "Exemples :"
    echo "  $0 concept 0.8   -> eval score chute -> alerte Grafana"
    echo "  $0 pipeline 0.7  -> TTFT > 3s -> heatmap s'emballe"
    echo "  $0 data 0.6      -> token spike -> injection simulee"
    echo "  $0 all 0.5       -> les 3 derives simultanement"
    echo "  $0 inject        -> simulation prompt injection"
    echo "  $0 reset         -> retour baseline"
    ;;
esac
