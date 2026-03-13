"""
LLM Observability Lab
"""
import asyncio, random, time, json, os, math
from contextlib import asynccontextmanager, nullcontext
from typing import Optional
from fastapi import FastAPI
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel
from prometheus_client import (
    Counter, Histogram, Gauge,
    generate_latest, CONTENT_TYPE_LATEST,
)

# Metriques

TTFT        = Histogram("llm_ttft_seconds",         "Time To First Token",   ["model"],
    buckets=[.05,.1,.2,.3,.5,.75,1,1.5,2,3,5,8,15])
TOKENS_IN   = Counter(  "llm_input_tokens_total",   "Tokens input",          ["model"])
TOKENS_OUT  = Counter(  "llm_output_tokens_total",  "Tokens output",         ["model"])
COST        = Counter(  "llm_cost_usd_total",        "Cout USD",              ["model"])
ERRORS      = Counter(  "llm_errors_total",          "Erreurs",               ["model","error_type"])
REQUESTS    = Counter(  "llm_requests_total",        "Requetes",              ["model","status"])
EVAL        = Gauge(    "llm_eval_score",            "Score qualite 0-1",     ["model"])
HALLUC_RATE = Gauge(    "llm_hallucination_rate",    "Taux hallucination",    ["model"])
RAG_SCORE   = Gauge(    "llm_rag_score",             "Score RAG",             ["model"])
RAG_LAT     = Histogram("llm_rag_latency_seconds",  "Latence RAG",           ["model"],
    buckets=[.03,.05,.1,.2,.5,1,2,3,5,8])
PROMPT_LEN  = Histogram("llm_prompt_chars",          "Longueur prompt",       ["model"],
    buckets=[50,100,200,400,800,1600,3200])
DRIFT_FLAG  = Gauge(    "llm_drift_active",          "Intensite derive 0-1",  ["drift_type"])
SESSIONS    = Gauge(    "llm_active_sessions",       "Sessions actives")
SATISFACTION= Gauge(    "llm_user_satisfaction",     "Score satisfaction",    ["model"])
COST_PER_Q  = Gauge(    "llm_cost_per_quality",      "USD par unite qualite", ["model"])

MODELS      = ["gpt-4o","gpt-4o-mini","llama-3","mistral"]
ERROR_TYPES = ["timeout","context_window","safety_refusal","json_invalid","rate_limit"]

COST_MAP = {
    "gpt-4o":      (5e-6,  15e-6),
    "gpt-4o-mini": (1.5e-7, 6e-7),
    "llama-3":     (2e-7,   2e-7),
    "mistral":     (3e-7,   3e-7),
}

# Pre-initialisation — toutes les series presentes au demarrage
for m in MODELS:
    EVAL.labels(model=m).set(0.91)
    RAG_SCORE.labels(model=m).set(0.85)
    HALLUC_RATE.labels(model=m).set(0.02)
    SATISFACTION.labels(model=m).set(4.3)
    COST_PER_Q.labels(model=m).set(0.001)
    for et in ERROR_TYPES:
        ERRORS.labels(model=m, error_type=et)
    REQUESTS.labels(model=m, status="success")
    REQUESTS.labels(model=m, status="error")
    REQUESTS.labels(model=m, status="blocked")
for dt in ("data","concept","pipeline"):
    DRIFT_FLAG.labels(drift_type=dt).set(0)
SESSIONS.set(0)

# OTel traces (non-bloquant)
_tracer = None
try:
    from opentelemetry import trace as _trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    _ep = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    _tp = TracerProvider(resource=Resource({"service.name": "llm-demo-app"}))
    _tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=_ep, insecure=True)))
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as OTLPHTTPExporter
        _phoenix_ep = os.getenv("PHOENIX_ENDPOINT", "http://phoenix:6006/v1/traces")
        _tp.add_span_processor(BatchSpanProcessor(OTLPHTTPExporter(endpoint=_phoenix_ep)))
    except Exception as _pe:
        print(f"[Phoenix] desactive : {_pe}", flush=True)
    _trace.set_tracer_provider(_tp)
    _tracer = _trace.get_tracer(__name__)
except Exception as e:
    print(f"[OTel] traces desactivees : {e}", flush=True)

def _span(name):
    return _tracer.start_as_current_span(name) if _tracer else nullcontext()

# Donnees de simulation

GOOD = [
    "Le conge paternite est de 28 jours depuis juillet 2021.",
    "Le produit X est a 1250 EUR HT, livraison 5 jours ouvrables.",
    "Pour un remboursement appelez le 0800 XXX XXX.",
    "Les retours sont acceptes sous 30 jours sur justificatif.",
    "Votre contrat se termine le 31/12/2026 avec renouvellement auto.",
    "Le teletravail est autorise 2 jours par semaine sur accord manager.",
    "Le plan epargne entreprise offre un abondement de 50%.",
    "Votre prime annuelle est calculee sur la base du salaire brut de decembre.",
]
BAD = [
    "Le conge paternite est de 2 jours selon la convention collective.",
    "Le produit X coute 450 EUR, disponible immediatement.",
    "Contactez le support via le formulaire en ligne.",
    "Les retours ne sont acceptes que dans les 7 jours.",
    "Votre contrat a ete renouvele automatiquement en 2023.",
    "La prime est plafonnee a 500 EUR quel que soit le salaire.",
]
PROMPTS = [
    "Duree du conge paternite ?",
    "Remboursement frais transport ?",
    "Preavis en cas de demission ?",
    "Horaires service client ?",
    "Bulletin de salaire en ligne ?",
    "Avantages salaries seniors ?",
    "Modifier mon adresse dans le RH ?",
    "Formations disponibles ce trimestre ?",
    "Politique de teletravail ?",
    "Declarer un arret maladie ?",
    "Regles heures supplementaires ?",
    "Plan epargne entreprise ?",
    "Conge sans solde : conditions ?",
    "Mutuelle : couverture famille ?",
    "Comment acceder au coffre numerique ?",
    "Prime de fin d annee : calcul ?",
    "Procedure de depart en retraite ?",
    "Conge maternite : duree et indemnisation ?",
]

# Etat global

class _S:
    data = False; concept = False; pipeline = False
    intensity   = 0.0
    eval_target = 0.91;  EVAL_BASE = 0.91
    ttft_target = 0.28;  TTFT_BASE = 0.28
    count       = 0
    active_sess = set()

S = _S()

def jlog(ev, **kw):
    print(json.dumps({"t": round(time.time(), 3), "ev": ev, **kw}), flush=True)

# Pattern de trafic

def traffic_intensity() -> float:
    # Cycle de 24 minutes en demo (1 minute = 1 heure simulee)
    h = (time.time() % 1440) / 60
    base = 0.3
    base += 0.6 * math.exp(-((h - 9)  ** 2) / 2)
    base += 0.5 * math.exp(-((h - 17) ** 2) / 2)
    base += 0.3 * math.exp(-((h - 14) ** 2) / 3)
    base -= 0.2 * math.exp(-((h - 12.5) ** 2) / 1)
    base += random.gauss(0, 0.05)
    return max(0.1, min(1.0, base))

def sleep_for_traffic() -> float:
    base = 0.4 / traffic_intensity()
    return max(0.2, random.gauss(base, base * 0.3))

# Logique requete

async def run_query(prompt: str, model: str, use_rag: bool, session: str) -> dict:
    S.count += 1
    S.active_sess.add(session)
    SESSIONS.set(len(S.active_sess))

    extra = int(len(prompt) * S.intensity * random.uniform(2, 4)) if S.data else 0
    n_in  = (len(prompt) + extra) // 4 + random.randint(30, 100)
    PROMPT_LEN.labels(model=model).observe(len(prompt) + extra)

    if use_rag:
        with _span("rag.retrieval"):
            if S.pipeline:
                lat = max(.1, random.gauss(S.ttft_target * 0.6, 0.6))
                sc  = max(.05, min(1, random.gauss(.38, .10)))
            else:
                lat = max(.02, random.gauss(.11, .025))
                sc  = max(.4,  min(1, random.gauss(.86, .04)))
            await asyncio.sleep(lat)
            RAG_LAT.labels(model=model).observe(lat)
            RAG_SCORE.labels(model=model).set(sc)

    with _span("llm.inference"):
        if S.pipeline:
            ttft = max(.1, random.gauss(S.ttft_target, S.intensity * 1.2))
        else:
            ttft = max(.04, random.gauss(S.ttft_target, .055))
        await asyncio.sleep(min(ttft, 1.5))
        halluc = S.concept and random.random() < S.intensity * 0.72
        resp   = random.choice(BAD if halluc else GOOD)
        n_out  = len(resp) // 4 + random.randint(10, 50)

    with _span("eval.judge"):
        noise = random.gauss(0, .065 if S.concept else .022)
        ev    = max(.05, min(.99, S.eval_target + noise))
        EVAL.labels(model=model).set(ev)

    if halluc:
        ERRORS.labels(model=model, error_type="safety_refusal").inc()

    h_rate = S.intensity * 0.72 * 0.5 if S.concept else 0.02 + random.gauss(0, .005)
    HALLUC_RATE.labels(model=model).set(max(0, min(1, h_rate)))

    sat = 4.5 - (1 - ev) * 2.5 - max(0, ttft - 1.0) * 0.3 + random.gauss(0, .1)
    SATISFACTION.labels(model=model).set(max(1.0, min(5.0, sat)))

    ci, co = COST_MAP.get(model, (3e-6, 9e-6))
    cost   = n_in * ci + n_out * co

    TTFT.labels(model=model).observe(ttft)
    TOKENS_IN.labels(model=model).inc(n_in)
    TOKENS_OUT.labels(model=model).inc(n_out)
    COST.labels(model=model).inc(cost)
    REQUESTS.labels(model=model, status="success").inc()
    COST_PER_Q.labels(model=model).set(cost / max(0.01, ev))

    # Erreurs de fond rares (~1%)
    if random.random() < (0.02 + S.intensity * 0.04 if S.pipeline else 0.01):
        ERRORS.labels(model=model, error_type=random.choice(ERROR_TYPES)).inc()

    jlog("req", m=model, s=session, ttft=round(ttft,3),
         eval_score=round(ev,3), cost=round(cost,6), halluc=halluc)

    async def release():
        await asyncio.sleep(random.uniform(3, 20))
        S.active_sess.discard(session)
        SESSIONS.set(len(S.active_sess))
    asyncio.create_task(release())

    return dict(response=resp, ttft=round(ttft,3), eval=round(ev,3),
                cost=round(cost,6), hallucination=halluc)

# Trafic de fond

async def bg():
    await asyncio.sleep(1)

    # Warmup : 20 requetes + erreurs initiales pour peupler tous les panels
    for i in range(20):
        try:
            await run_query(random.choice(PROMPTS), MODELS[i % len(MODELS)], True, f"warmup-{i}")
        except Exception:
            pass
        await asyncio.sleep(0.1)

    for m, et in [("gpt-4o","timeout"), ("gpt-4o-mini","rate_limit"),
                  ("llama-3","json_invalid"), ("mistral","context_window"),
                  ("gpt-4o","safety_refusal")]:
        ERRORS.labels(model=m, error_type=et).inc()
        REQUESTS.labels(model=m, status="error").inc()

    burst_countdown = random.randint(20, 60)
    while True:
        try:
            burst_countdown -= 1
            if burst_countdown <= 0:
                n = random.randint(5, 10)
                jlog("traffic.burst", size=n)
                for _ in range(n):
                    asyncio.create_task(run_query(
                        random.choice(PROMPTS), random.choice(MODELS),
                        True, f"burst-{random.randint(1,20)}"
                    ))
                    await asyncio.sleep(0.05)
                burst_countdown = random.randint(30, 90)
            else:
                await run_query(
                    random.choice(PROMPTS), random.choice(MODELS),
                    random.random() > .18, f"bg-{random.randint(1,60)}"
                )
        except Exception as e:
            jlog("bg_err", err=str(e))
        await asyncio.sleep(sleep_for_traffic())

@asynccontextmanager
async def lifespan(app):
    t = asyncio.create_task(bg())
    yield
    t.cancel()
    try: await t
    except asyncio.CancelledError: pass

# Pydantic

class QReq(BaseModel):
    prompt: str
    model: str = "gpt-4o"
    use_rag: bool = True
    session_id: Optional[str] = None

class DReq(BaseModel):
    drift_type: str
    intensity: float = 0.6

class AnnotationReq(BaseModel):
    text: str
    tags: list[str] = []

# FastAPI

app = FastAPI(title="LLM Observability Demo", lifespan=lifespan)

GRAFANA_URL  = os.getenv("GRAFANA_URL",  "http://grafana:3000")
GRAFANA_USER = os.getenv("GRAFANA_USER", "admin")
GRAFANA_PASS = os.getenv("GRAFANA_PASS", "admin")

async def post_grafana_annotation(text: str, tags: list[str]):
    try:
        import urllib.request, base64
        payload = json.dumps({
            "dashboardUID": "llm-obs",
            "time": int(time.time() * 1000),
            "tags": tags,
            "text": text,
        }).encode()
        auth = base64.b64encode(f"{GRAFANA_USER}:{GRAFANA_PASS}".encode()).decode()
        req = urllib.request.Request(
            f"{GRAFANA_URL}/api/annotations",
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            jlog("grafana.annotation", text=text, status=r.status)
    except Exception as e:
        jlog("grafana.annotation.err", err=str(e))

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/health")
def health():
    return {"ok": True, "requests": S.count, "active_sessions": len(S.active_sess)}

@app.get("/status")
def status():
    return {
        "requests": S.count,
        "active_sessions": len(S.active_sess),
        "traffic_intensity": round(traffic_intensity(), 2),
        "drift": {
            "data": S.data, "concept": S.concept, "pipeline": S.pipeline,
            "intensity": S.intensity,
            "eval_target": round(S.eval_target, 3),
            "ttft_target": round(S.ttft_target, 3),
        }
    }

@app.post("/query")
async def query(r: QReq):
    res = await run_query(r.prompt, r.model, r.use_rag, r.session_id or "anon")
    res["drift"] = {"data": S.data, "concept": S.concept, "pipeline": S.pipeline}
    return res

@app.post("/drift")
async def drift(r: DReq):
    if r.drift_type == "reset":
        was_active = S.data or S.concept or S.pipeline
        S.data = S.concept = S.pipeline = False
        S.intensity = 0.0
        S.eval_target = S.EVAL_BASE
        S.ttft_target = S.TTFT_BASE
        for dt in ("data","concept","pipeline"):
            DRIFT_FLAG.labels(drift_type=dt).set(0)
        for m in MODELS:
            HALLUC_RATE.labels(model=m).set(0.02)
        jlog("drift.reset")
        if was_active:
            asyncio.create_task(post_grafana_annotation("reset - retour baseline", ["drift","reset"]))
        return {"status": "reset"}

    S.intensity = min(1.0, max(0.1, r.intensity))
    msgs = []; tags = ["drift"]

    if r.drift_type in ("data","all"):
        S.data = True
        DRIFT_FLAG.labels(drift_type="data").set(S.intensity)
        msgs.append(f"data drift actif (intensity={S.intensity})")
        tags.append("data-drift")

    if r.drift_type in ("concept","all"):
        S.concept = True
        DRIFT_FLAG.labels(drift_type="concept").set(S.intensity)
        S.eval_target = S.EVAL_BASE * (1 - S.intensity * 0.45)
        msgs.append(f"concept drift - eval cible {S.eval_target:.2f}")
        tags.append("concept-drift")

    if r.drift_type in ("pipeline","all"):
        S.pipeline = True
        DRIFT_FLAG.labels(drift_type="pipeline").set(S.intensity)
        S.ttft_target = S.TTFT_BASE + S.intensity * 4.0
        msgs.append(f"pipeline drift - TTFT cible {S.ttft_target:.2f}s")
        tags.append("pipeline-drift")

    label = " + ".join(t.replace("-"," ") for t in tags if t != "drift")
    asyncio.create_task(post_grafana_annotation(f"{label} (intensity={S.intensity})", tags))
    jlog("drift.on", type=r.drift_type, intensity=S.intensity)
    return {"status": "activated", "messages": msgs}

@app.post("/annotation")
async def annotation(r: AnnotationReq):
    asyncio.create_task(post_grafana_annotation(r.text, r.tags))
    return {"status": "posted", "text": r.text}

@app.post("/inject")
async def inject():
    toks = random.randint(900, 2500)
    TOKENS_IN.labels(model="gpt-4o").inc(toks)
    ERRORS.labels(model="gpt-4o", error_type="prompt_injection").inc()
    REQUESTS.labels(model="gpt-4o", status="blocked").inc()
    asyncio.create_task(post_grafana_annotation(
        f"prompt injection - token spike +{toks}", ["security","injection"]
    ))
    jlog("injection", level="CRITICAL", token_spike=toks)
    return {"status": "blocked", "token_spike": toks}

@app.post("/error/{etype}")
def sim_error(etype: str):
    if etype not in ERROR_TYPES:
        return JSONResponse(status_code=400, content={"valid": ERROR_TYPES})
    ERRORS.labels(model="gpt-4o", error_type=etype).inc()
    REQUESTS.labels(model="gpt-4o", status="error").inc()
    jlog("llm.error", etype=etype)
    return {"status": "simulated", "type": etype}
