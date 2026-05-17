"""Budowanie grafu BFS przeplywu transakcji.

Co to robi:
- zaczyna od `root_address`,
- iteruje BFS przez `hops` poziomow,
- dla kazdego adresu pobiera transakcje (ETH + ERC-20) przez Etherscan,
- zbiera unikalne adresy do `nodes` i transakcje jako `edges`,
- pomija (nie ekspanduje dalej) znanych terminali (Tornado/CEX/bridge) bo to naturalne konce sledzenia.

Czemu BFS a nie DFS:
- BFS gwarantuje ze wszystkie wezly na poziomie `n` sa znalezione zanim ruszymy na `n+1`,
- latwiej kontrolowac glebokosc i koszt zapytan,
- ladniejszy layout na froncie (warstwy koncentryczne).

Limity zapytan:
- hop 0: 1 zapytanie (root)
- hop 1: ~max_per_hop * 1 = ~20 zapytan
- hop 2: ~max_per_hop * unique_counterparties = ~20-50 zapytan
- hop 3: szybko rosnie - dlatego cap i dedup.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from functools import lru_cache
from pathlib import Path

from loguru import logger

from forensics.clients.etherscan import EtherscanClient, EtherscanError
from forensics.core.models import GraphEdge, GraphNode, TraceGraph, Transaction

_KNOWN_ADDRESSES_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "known_addresses"
)


@lru_cache(maxsize=1)
def _load_known_endpoints() -> set[str]:
    """Laduje wszystkie adresy ktore traktujemy jako terminale (nie ekspandujemy ich dalej).

    Mixery, bridges, CEX - to sa naturalne konce sledzenia. Tornado Cash pool ma setki tysiecy
    transakcji, ekspandowanie go zalalo by graf bezsensem. Komentarz w pracy mgr:
    "moment ukrycia/cashout = naturalna terminacja BFS".
    """
    endpoints: set[str] = set()
    if not _KNOWN_ADDRESSES_DIR.exists():
        logger.warning("Brak katalogu known_addresses: {}", _KNOWN_ADDRESSES_DIR)
        return endpoints

    for json_file in _KNOWN_ADDRESSES_DIR.glob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Nie udalo sie zaladowac {}: {}", json_file.name, exc)
            continue
        for entry in data.get("addresses", []):
            endpoints.add(entry["address"].lower())
    logger.info("Znanych endpoints (terminali BFS): {}", len(endpoints))
    return endpoints


async def build_trace_graph(
    etherscan: EtherscanClient,
    root_address: str,
    hops: int = 2,
    root_max_tx: int = 50,
    per_hop_max_tx: int = 20,
) -> tuple[list[Transaction], TraceGraph]:
    """BFS przez `hops` poziomow z root_address.

    Returns:
        (wszystkie_zebrane_transakcje, TraceGraph)
    """
    root = root_address.lower()
    endpoints = _load_known_endpoints()

    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    seen_edges: set[tuple[str, str, str]] = set()
    visited: set[str] = set()  # adresy ktore juz zapytalismy
    all_txs: list[Transaction] = []
    seen_tx_keys: set[tuple[str, str, str, str]] = set()  # dedup transakcji

    queue: deque[tuple[str, int]] = deque([(root, 0)])
    nodes[root] = GraphNode(address=root, depth=0, is_root=True)

    while queue:
        addr, depth = queue.popleft()
        if addr in visited:
            continue
        visited.add(addr)

        node = nodes.setdefault(addr, GraphNode(address=addr, depth=depth))
        node.depth = min(node.depth, depth)  # zachowaj minimalna glebokosc

        # Endpoints - pokazujemy w grafie ale nie ekspandujemy
        if addr != root and addr in endpoints:
            node.is_endpoint = True
            continue

        # Czy ekspandujemy ten poziom?
        if depth >= hops:
            continue

        # Pobierz transakcje adresu
        limit = root_max_tx if addr == root else per_hop_max_tx
        try:
            normal, tokens = await asyncio.gather(
                etherscan.get_normal_transactions(addr, offset=limit // 2 or 10),
                etherscan.get_token_transfers(addr, offset=limit // 2 or 10),
            )
        except EtherscanError as exc:
            logger.warning("Etherscan blad dla {} (depth={}): {}", addr, depth, exc)
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("Unexpected blad dla {}: {}", addr, exc)
            continue

        txs = sorted([*normal, *tokens], key=lambda t: t.block_number, reverse=True)[:limit]

        # Dedup po (hash, from, to, token_contract) - BFS moze pobrac te sama tx
        # przy roozcie i przy sasiedzie ktory byl jej druga strona.
        deduped: list[Transaction] = []
        for tx in txs:
            key = (
                tx.hash,
                tx.from_address.lower(),
                (tx.to_address or "").lower(),
                tx.token_contract or "eth",
            )
            if key in seen_tx_keys:
                continue
            seen_tx_keys.add(key)
            deduped.append(tx)

        all_txs.extend(deduped)
        node.tx_count = len(txs)
        txs = deduped

        for tx in txs:
            from_addr = tx.from_address.lower()
            to_addr = (tx.to_address or "").lower()
            if not to_addr or not from_addr:
                continue

            # Dodaj counterparty jako node
            for cp in (from_addr, to_addr):
                if cp == addr:
                    continue
                if cp not in nodes:
                    nodes[cp] = GraphNode(address=cp, depth=depth + 1)
                else:
                    nodes[cp].depth = min(nodes[cp].depth, depth + 1)

                # Queue do ekspansji jesli jest miejsce na kolejny hop
                if cp not in visited and depth + 1 < hops:
                    queue.append((cp, depth + 1))

            # Dodaj edge (dedup po hash + from + to bo jeden hash moze mieć multi-transfer)
            edge_key = (from_addr, to_addr, tx.hash)
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                edges.append(
                    GraphEdge(
                        source=from_addr,
                        target=to_addr,
                        tx_hash=tx.hash,
                        value=tx.value_eth,
                        token=tx.token_symbol,
                        block=tx.block_number,
                    )
                )

    graph = TraceGraph(
        nodes=list(nodes.values()),
        edges=edges,
        root_address=root,
        hops=hops,
        fetched_addresses=len(visited),
    )
    return all_txs, graph
