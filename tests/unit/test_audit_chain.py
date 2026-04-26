"""
中文：Audit chain 单元测试，验证正常链路通过校验且篡改会被发现。
English: Audit chain unit tests verifying valid chains pass and tampered entries are detected.
"""

from origami.audit.chain import AuditChain


def test_audit_chain_verifies() -> None:
    chain = AuditChain()
    chain.append(
        run_id="test",
        step=0,
        observation={"x": 1},
        proposed_action={"move": "east"},
        final_action={"move": "east"},
    )

    assert chain.verify() == (True, -1)


def test_audit_chain_detects_tampering() -> None:
    chain = AuditChain()
    entry = chain.append(
        run_id="test",
        step=0,
        observation={"x": 1},
        proposed_action={"move": "east"},
        final_action={"move": "east"},
    )
    entry.data["step"] = 99

    assert chain.verify() == (False, 0)
