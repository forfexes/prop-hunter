#!/usr/bin/env python3
"""Probe public SHL Statnet reports before enabling persistence."""
from __future__ import annotations
import re
import requests
import urllib3

URL = "https://reports.statnet.se/shl/"
HEADERS = {"User-Agent": "PROP-HUNTER/shl-probe", "Accept": "text/html,*/*"}


def main():
    # This public read-only Statnet host currently serves an incomplete TLS
    # certificate chain on GitHub runners. Scope verification bypass to this
    # single hard-coded host only; never generalize it to other requests.
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    r=requests.get(URL,timeout=15,headers=HEADERS,verify=False)
    print("SHL_STATNET_INDEX",r.status_code,len(r.text),r.url,flush=True)
    r.raise_for_status()
    hrefs=re.findall(r'href=["\']([^"\']+)["\']',r.text,re.I)
    texts=re.findall(r'>([^<>]{1,120}PlayerReport[^<>]{0,120})<',r.text,re.I)
    player_links=[h for h in hrefs if "player" in h.lower() and ("report" in h.lower() or "stats" in h.lower())]
    print("SHL_STATNET_HREFS",len(hrefs),flush=True)
    print("SHL_STATNET_PLAYER_LINKS",player_links[:20],flush=True)
    print("SHL_STATNET_TEXTS",texts[:20],flush=True)
    print("SHL_STATNET_HREF_SAMPLE",hrefs[:80],flush=True)
    if player_links:
        from urllib.parse import urljoin
        from io import BytesIO
        from pypdf import PdfReader
        pdf_url=urljoin(URL,player_links[0])
        pr=requests.get(pdf_url,timeout=20,headers=HEADERS,verify=False)
        print("SHL_PLAYERREPORT_PDF",pr.status_code,len(pr.content),pdf_url,flush=True)
        pr.raise_for_status()
        reader=PdfReader(BytesIO(pr.content))
        text="\n".join((page.extract_text() or "") for page in reader.pages)
        print("SHL_PLAYERREPORT_TEXT_BEGIN",flush=True)
        print("\n".join(text.splitlines()[:180]),flush=True)
        print("SHL_PLAYERREPORT_TEXT_END",flush=True)
        import pdfplumber
        with pdfplumber.open(BytesIO(pr.content)) as pdf:
            for page_no,page in enumerate(pdf.pages[:2],1):
                tables=page.extract_tables()
                print(f"SHL_TABLE_PAGE {page_no} TABLES {len(tables)}",flush=True)
                for table_no,table in enumerate(tables[:4],1):
                    print(f"SHL_TABLE_BEGIN page={page_no} table={table_no}",flush=True)
                    for row in table[:40]:
                        print("SHL_TABLE_ROW",repr(row),flush=True)
                    print("SHL_TABLE_END",flush=True)


if __name__=="__main__":
    main()
