from forensics.clients.etherscan import EtherscanClient


def test_parse_normal_transaction_converts_wei_to_eth() -> None:
    raw = {
        "hash": "0xabc",
        "blockNumber": "123",
        "timeStamp": "1700000000",
        "from": "0xABCDEF",
        "to": "0xFEDCBA",
        "value": str(10**18),
        "gasUsed": "21000",
        "isError": "0",
    }

    tx = EtherscanClient._parse_transaction(raw)

    assert tx.hash == "0xabc"
    assert tx.block_number == 123
    assert tx.from_address == "0xabcdef"
    assert tx.to_address == "0xfedcba"
    assert tx.value_eth == 1.0
    assert tx.token_symbol is None


def test_parse_token_transfer_uses_token_decimals() -> None:
    raw = {
        "hash": "0xtoken",
        "blockNumber": "456",
        "timeStamp": "1700000000",
        "from": "0xAAAA",
        "to": "0xBBBB",
        "value": "1234500",
        "gasUsed": "90000",
        "tokenSymbol": "USDC",
        "tokenName": "USD Coin",
        "contractAddress": "0xA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48",
        "tokenDecimal": "6",
    }

    tx = EtherscanClient._parse_token_transfer(raw)

    assert tx.hash == "0xtoken"
    assert tx.block_number == 456
    assert tx.value_eth == 1.2345
    assert tx.token_symbol == "USDC"
    assert tx.token_decimals == 6
    assert tx.token_contract == "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
