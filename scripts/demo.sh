#!/bin/sh
# demo.sh - Scenario de demonstration demo
# 
# Usage : ./scripts/demo.sh [step]
# Sans argument : sequence complete automatique

URL="http://localhost:8000"
BOLD="\033[1m"
RED="\033[31m"
YEL="\033[33m"
GRN="\033[32m"
CYN="\033[36m"
RST="\033[0m"

say() { printf "${BOLD}${CYN}[DEMO]${RST} $1\n"; }
ok()  { printf "${GRN}[OK]${RST}   $1\n"; }
warn(){ printf "${YEL}[>>>]${RST}  $1\n"; }
alert(){ printf "${RED}[!!!]${RST}  $1\n"; }

pause() {
    printf "\n${BOLD}Appuyer sur ENTER pour continuer...${RST}\n"
    read _
}

wait_s() {
    printf "  Attente ${1}s"
    i=0; while [ $i -lt $1 ]; do printf "."; sleep 1; i=$((i+1)); done
    printf " done\n"
}

check_app() {
    if ! curl -sf "$URL/health" > /dev/null 2>&1; then
        alert "L app n est pas accessible sur $URL"
        alert "Lancer : docker compose up -d --build"
        exit 1
    fi
}

show_metrics() {
    printf "\n  Metriques actuelles :\n"
    STATUS=$(curl -sf "$URL/status")
    echo "$STATUS" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(f'    Requetes totales    : {d[\"requests\"]}')
print(f'    Sessions actives    : {d[\"active_sessions\"]}')
print(f'    Intensite trafic    : {d[\"traffic_intensity\"]}')
drift=d['drift']
print(f'    Derives actives     : data={drift[\"data\"]} concept={drift[\"concept\"]} pipeline={drift[\"pipeline\"]}')
print(f'    Eval target         : {drift[\"eval_target\"]:.2f}')
print(f'    TTFT target         : {drift[\"ttft_target\"]:.2f}s')
" 2>/dev/null || echo "    (parsing error)"
}

# ────────────────────────────────────────────────────────────────────
# ETAPES
# ────────────────────────────────────────────────────────────────────

step_0_reset() {
    say "RESET - Retour au baseline propre"
    curl -sf -X POST "$URL/drift" -H "Content-Type: application/json" \
        -d '{"drift_type":"reset"}' > /dev/null
    ok "Toutes les derives desactivees"
    curl -sf -X POST "$URL/annotation" -H "Content-Type: application/json" \
        -d '{"text":"DEMO START - baseline propre","tags":["demo","start"]}' > /dev/null 2>&1
    wait_s 5
    show_metrics
}

step_1_baseline() {
    say "ETAPE 1 - Baseline : LLM en production, tout va bien"
    warn "Dans Grafana : eval score stable ~0.91, TTFT P99 < 0.5s, hallucination < 3%"
    warn "Le trafic de fond simule des utilisateurs reels avec patterns variables"
    warn "Observez les bursts occasionnels sur le panel Requetes/min"
    wait_s 15
    show_metrics
}

step_2_concept_drift() {
    say "ETAPE 2 - Concept Drift : le modele commence a halluciner"
    warn "Scenario : mise a jour silencieuse du provider LLM la nuit derniere"
    warn "Aucune alerte infra. CPU normal. RAM normale. SLO latence OK."
    warn "Mais les reponses deviennent fausses..."
    pause

    say "Activation concept drift (intensity=0.75)"
    RESULT=$(curl -sf -X POST "$URL/drift" -H "Content-Type: application/json" \
        -d '{"drift_type":"concept","intensity":0.75}')
    echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); [print(f'  -> {m}') for m in d['messages']]" 2>/dev/null

    warn "Annotation Grafana postee - regarder la ligne rouge sur les panels"
    wait_s 20

    alert "Ce que vous voyez dans Grafana :"
    alert "  eval_score chute de 0.91 -> ~0.50"
    alert "  hallucination_rate monte de 2% -> ~30%"
    alert "  user_satisfaction passe de 4.5 -> ~3.2"
    alert "  TTFT reste normal - impossible a detecter avec monitoring infra seul"
    show_metrics
}

step_3_pipeline_drift() {
    pause
    say "ETAPE 3 - Pipeline Drift : le RAG se degrade"
    warn "Scenario : mise a jour du chunk_size RAG de 500 -> 1000 tokens en prod"
    warn "Pensee : plus de contexte = meilleures reponses. Resultat : TTFT x10."
    warn "Le reranking prend maintenant 6s sur 8s de latence totale."
    pause

    say "Reset concept drift, activation pipeline drift (intensity=0.7)"
    curl -sf -X POST "$URL/drift" -H "Content-Type: application/json" \
        -d '{"drift_type":"reset"}' > /dev/null
    wait_s 3
    RESULT=$(curl -sf -X POST "$URL/drift" -H "Content-Type: application/json" \
        -d '{"drift_type":"pipeline","intensity":0.7}')
    echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); [print(f'  -> {m}') for m in d['messages']]" 2>/dev/null

    wait_s 25

    alert "Ce que vous voyez dans Grafana :"
    alert "  TTFT P99 : 0.3s -> >3s - alerte declenchee"
    alert "  Heatmap TTFT : toute la distribution decale vers la droite"
    alert "  RAG score : chute (contexte trop large = bruit)"
    alert "  RAG latency P99 : spike visible"
    alert "  Eval score : commence a baisser (RAG degrade)"
    show_metrics
}

step_4_injection() {
    pause
    say "ETAPE 4 - Securite : simulation prompt injection"
    warn "Scenario : un utilisateur tente de bypasser les guardrails"
    warn "Token spike anormal detecte, requete bloquee, annotation Grafana"
    pause

    say "Envoi d une tentative d injection..."
    RESULT=$(curl -sf -X POST "$URL/inject")
    echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'  Bloquee - token spike : +{d[\"token_spike\"]} tokens')" 2>/dev/null

    alert "Dans Grafana : spike immediat sur llm_input_tokens_total"
    alert "Annotation rouge : Prompt injection detectee"
    wait_s 10
}

step_5_all() {
    pause
    say "ETAPE 5 - Tempete parfaite : les 3 derives simultanement"
    warn "Scenario cauchemar : vendredi 17h en prod"
    pause

    say "Activation ALL DRIFT (intensity=0.6)"
    curl -sf -X POST "$URL/drift" -H "Content-Type: application/json" \
        -d '{"drift_type":"reset"}' > /dev/null
    wait_s 2
    RESULT=$(curl -sf -X POST "$URL/drift" -H "Content-Type: application/json" \
        -d '{"drift_type":"all","intensity":0.6}')
    echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); [print(f'  -> {m}') for m in d['messages']]" 2>/dev/null

    wait_s 30

    alert "Toutes les alertes actives - 4 panneaux rouges/orange simultanement"
    alert "Sans observabilite LLM : invisible dans vos dashboards infra"
    show_metrics
}

step_6_reset() {
    pause
    say "ETAPE 6 - Resolution : retour baseline"
    warn "En production : rollback provider + rollback RAG config"
    pause

    curl -sf -X POST "$URL/drift" -H "Content-Type: application/json" \
        -d '{"drift_type":"reset"}' > /dev/null
    curl -sf -X POST "$URL/annotation" -H "Content-Type: application/json" \
        -d '{"text":"RESOLUTION - rollback effectue, retour baseline","tags":["demo","resolution"]}' > /dev/null 2>&1

    wait_s 15
    ok "Derive resorbee - toutes les metriques reviennent au baseline"
    ok "Temps de detection : visible en <30s avec observabilite LLM"
    ok "Sans observabilite LLM : detection apres retours clients (24-48h)"
    show_metrics
}

# ────────────────────────────────────────────────────────────────────
# ENTRYPOINT
# ────────────────────────────────────────────────────────────────────

check_app

case "${1:-full}" in
    full)
        printf "\n${BOLD}=== DEMO LLM Observability - demo 2026 ===${RST}\n"
        printf "${BOLD}===  ===${RST}\n\n"
        step_0_reset
        step_1_baseline
        step_2_concept_drift
        step_3_pipeline_drift
        step_4_injection
        step_5_all
        step_6_reset
        printf "\n${BOLD}${GRN}=== FIN DE LA DEMO ===${RST}\n"
        ;;
    reset)    step_0_reset ;;
    baseline) step_1_baseline ;;
    concept)  step_0_reset; step_2_concept_drift ;;
    pipeline) step_0_reset; step_3_pipeline_drift ;;
    inject)   step_4_injection ;;
    all)      step_0_reset; step_5_all ;;
    status)   check_app; show_metrics ;;
    *)
        echo "Usage: $0 [full|reset|baseline|concept|pipeline|inject|all|status]"
        echo ""
        echo "  full      : sequence complete (~5 min)"
        echo "  concept   : demo concept drift seul"
        echo "  pipeline  : demo pipeline drift seul"
        echo "  inject    : demo injection seul"
        echo "  all       : les 3 derives en meme temps"
        echo "  status    : etat actuel des metriques"
        ;;
esac
