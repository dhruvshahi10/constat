"""Prepare an Atlan tenant for Constat, idempotently.

    python scripts/atlan_setup.py --glossary "Security Claims" --create-cm            # glossary + custom metadata set
    python scripts/atlan_setup.py --seed evals/golden/claims_acme.json --approver fde@atlan.com
    python scripts/atlan_setup.py --dry-run --seed claims.json                          # print what would be written

Needs ATLAN_BASE_URL and ATLAN_API_KEY (pyatlan reads them) unless --dry-run.
What it creates: a glossary that holds one term per claim; a custom metadata
set "Claim" with the attributes in constat.claims.atlan.CM_ATTRIBUTES; the
terms themselves with certificate status and custom metadata. It refuses to
overwrite an existing term.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constat.claims import Claim  # noqa: E402
from constat.claims.atlan import CM_ATTRIBUTES, CM_SET, to_term_payload  # noqa: E402

PYATLAN_TYPES = {"Text": "STRING", "Options": "OPTIONS", "Date": "DATE", "Integer": "INTEGER",
                 "Rich text": "STRING", "Boolean": "BOOLEAN", "URL": "URL", "Users": "USERS"}


def plan(claims: list[Claim], glossary: str) -> dict:
    return {
        "glossary": glossary,
        "custom_metadata_set": {"name": CM_SET, "attributes": [{"name": k, "type": v, "pyatlan_type": PYATLAN_TYPES.get(v, "STRING")}
                                                                for k, v in CM_ATTRIBUTES.items()]},
        "terms": [to_term_payload(c) for c in claims],
    }


def apply(p: dict, approver: str, create_cm: bool) -> None:
    from pyatlan.client.atlan import AtlanClient  # type: ignore
    from pyatlan.model.assets import AtlasGlossary, AtlasGlossaryTerm  # type: ignore
    from pyatlan.model.enums import AtlanCustomAttributePrimitiveType, CertificateStatus  # type: ignore
    from pyatlan.model.typedef import AttributeDef, CustomMetadataDef  # type: ignore
    from pyatlan.model.custom_metadata import CustomMetadataDict  # type: ignore

    client = AtlanClient()
    try:
        glossary = client.asset.find_glossary_by_name(p["glossary"])
        print(f"glossary exists: {glossary.qualified_name}")
    except Exception:  # noqa: BLE001 - not found
        g = AtlasGlossary.creator(name=p["glossary"])
        g.description = "Constat security claims: one term per claim; certificate status is the approval state."
        glossary = client.asset.save(g).assets_created(asset_type=AtlasGlossary)[0]
        print(f"glossary created: {glossary.qualified_name}")

    if create_cm:
        try:
            client.custom_metadata_cache.get_id_for_name(CM_SET)
            print(f"custom metadata set exists: {CM_SET}")
        except Exception:  # noqa: BLE001 - not found
            cm = CustomMetadataDef.create(display_name=CM_SET)
            attrs = []
            for a in p["custom_metadata_set"]["attributes"]:
                t = getattr(AtlanCustomAttributePrimitiveType, a["pyatlan_type"], AtlanCustomAttributePrimitiveType.STRING)
                kwargs = {"display_name": a["name"], "attribute_type": t}
                if a["type"] == "Options":
                    kwargs["options_name"] = "constat_audience"
                attrs.append(AttributeDef.create(client=client, **kwargs))
            cm.attribute_defs = attrs
            client.typedef.create(cm)
            print(f"custom metadata set created: {CM_SET} ({len(attrs)} attributes)")

    for payload in p["terms"]:
        try:
            client.asset.find_term_by_name(payload["name"], glossary.qualified_name)
            print(f"skip existing term: {payload['name']}")
            continue
        except Exception:  # noqa: BLE001 - not found
            pass
        term = AtlasGlossaryTerm.creator(name=payload["name"], glossary_qualified_name=glossary.qualified_name)
        term.user_description = payload["user_description"]
        term.owner_users = set(payload["owner_users"])
        term.certificate_status = CertificateStatus[payload["certificate_status"]]
        cmd = CustomMetadataDict(client=client, name=CM_SET)
        for k, v in payload["custom_metadata"][CM_SET].items():
            cmd[k] = v
        term.set_custom_metadata(client=client, custom_metadata=cmd)
        client.asset.save(term)
        print(f"term created: {payload['name']} (approver {approver})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glossary", default="Security Claims")
    ap.add_argument("--create-cm", action="store_true")
    ap.add_argument("--seed", help="claims JSON ({claims: [...]})")
    ap.add_argument("--approver", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    claims = []
    if args.seed:
        spec = json.loads(Path(args.seed).read_text(encoding="utf-8"))
        claims = [Claim.from_dict(c) for c in spec["claims"]]
        for c in claims:
            problems = c.validate()
            if problems:
                print(f"refusing {c.claim_id}: {'; '.join(problems)}", file=sys.stderr)
                return 2
    p = plan(claims, args.glossary)
    if args.dry_run:
        print(json.dumps(p, indent=2, ensure_ascii=False)[:4000])
        print(f"... {len(p['terms'])} terms, {len(p['custom_metadata_set']['attributes'])} attributes")
        return 0
    if args.seed and not args.approver:
        print("--approver is required when seeding", file=sys.stderr)
        return 2
    try:
        apply(p, args.approver, args.create_cm)
    except ImportError:
        print("pyatlan is not installed: pip install pyatlan, then set ATLAN_BASE_URL and ATLAN_API_KEY", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
