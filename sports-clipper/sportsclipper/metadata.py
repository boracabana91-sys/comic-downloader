"""Title / description / tags. Uses Claude Haiku 5.5 if a key is set, otherwise a plain template."""
from __future__ import annotations
import json
import os
import urllib.request


def api_key(cfg: dict) -> str:
    return cfg["ai"].get("api_key") or os.environ.get(cfg["ai"]["api_key_env"], "")


def build(cfg: dict, source_title: str, source_name: str, kept_s: float, log=print) -> dict:
    fallback = {"title": f"{source_title} | Condensed Highlights"[:100],
                "description": f"Condensed live-play cut of: {source_title}\nSource: {source_name}\n",
                "tags": list(cfg.get("tags", []))[:30]}
    ai = cfg["ai"]
    if not ai["enabled"]:
        return fallback
    key = api_key(cfg)
    if not key:
        log("no Anthropic API key set - using plain titles (add it in config.json, see README)")
        return fallback
    prompt = (f"Write YouTube metadata for a condensed ({kept_s / 60:.1f} min) live-play cut of the video "
              f"titled '{source_title}' from {source_name}. Channel: {cfg.get('channel_name') or 'our channel'}. "
              "Return ONLY JSON: {\"title\": <=90 chars, specific and honest, no clickbait, \"description\": "
              "2-3 sentences and a line crediting the source, \"tags\": up to 12 short tags}.")
    body = json.dumps({"model": ai["model"], "max_tokens": 500,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        txt = json.load(urllib.request.urlopen(req, timeout=60))["content"][0]["text"]
        j = json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
        return {"title": str(j["title"])[:100], "description": str(j["description"]),
                "tags": (list(cfg.get("tags", [])) + list(j.get("tags", [])))[:30]}
    except Exception as e:  # a metadata hiccup must never stop the pipeline
        log(f"AI titles failed ({e}); using plain titles")
        return fallback
