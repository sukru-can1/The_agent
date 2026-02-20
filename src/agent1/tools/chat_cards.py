"""Google Chat Card V2 builders for interactive approval flows."""

from __future__ import annotations


def build_draft_approval_card(
    draft_id: int,
    subject: str,
    from_address: str,
    to_address: str,
    draft_body: str,
    classification: str,
) -> dict:
    """Build a Chat Card V2 with Approve / Revise / Edit / Reject for an email draft.

    Includes a text input for inline AI revision instructions.
    """
    # Truncate body for card preview
    preview = draft_body[:500] + "..." if len(draft_body) > 500 else draft_body
    draft_id_str = str(draft_id)

    return {
        "cardId": f"draft-{draft_id}",
        "card": {
            "header": {
                "title": f"Email Draft #{draft_id}",
                "subtitle": f"Classification: {classification}",
                "imageUrl": "https://fonts.gstatic.com/s/i/short-term/release/googlesymbols/mail/default/48px.svg",
                "imageType": "CIRCLE",
            },
            "sections": [
                {
                    "header": "Details",
                    "widgets": [
                        {
                            "decoratedText": {
                                "topLabel": "Subject",
                                "text": subject or "(no subject)",
                                "startIcon": {"knownIcon": "DESCRIPTION"},
                            }
                        },
                        {
                            "decoratedText": {
                                "topLabel": "From",
                                "text": from_address or "unknown",
                                "startIcon": {"knownIcon": "PERSON"},
                            }
                        },
                        {
                            "decoratedText": {
                                "topLabel": "To",
                                "text": to_address or "unknown",
                                "startIcon": {"knownIcon": "EMAIL"},
                            }
                        },
                    ],
                },
                {
                    "header": "Draft Response",
                    "widgets": [
                        {
                            "textParagraph": {
                                "text": f"<pre>{_escape_html(preview)}</pre>"
                            }
                        }
                    ],
                },
                # Inline revision input
                {
                    "header": "Refine with AI",
                    "collapsible": True,
                    "widgets": [
                        {
                            "textInput": {
                                "name": "revision_instruction",
                                "label": "Revision instruction",
                                "hintText": "e.g. make it more formal, add tracking info, shorter",
                                "type": "SINGLE_LINE",
                            }
                        },
                        {
                            "buttonList": {
                                "buttons": [
                                    {
                                        "text": "Revise Draft",
                                        "color": {
                                            "red": 0.50, "green": 0.36,
                                            "blue": 0.97, "alpha": 1,
                                        },
                                        "onClick": {
                                            "action": {
                                                "function": "revise_draft",
                                                "parameters": [
                                                    {"key": "draft_id", "value": draft_id_str},
                                                ],
                                                "loadIndicator": "SPINNER",
                                            }
                                        },
                                    },
                                ]
                            }
                        },
                    ],
                },
                # Action buttons
                {
                    "widgets": [
                        {
                            "buttonList": {
                                "buttons": [
                                    {
                                        "text": "Approve & Send",
                                        "color": {
                                            "red": 0.22, "green": 0.56,
                                            "blue": 0.24, "alpha": 1,
                                        },
                                        "onClick": {
                                            "action": {
                                                "function": "approve_draft",
                                                "parameters": [
                                                    {"key": "draft_id", "value": draft_id_str},
                                                ],
                                            }
                                        },
                                    },
                                    {
                                        "text": "Edit in Dashboard",
                                        "color": {
                                            "red": 0.10, "green": 0.46,
                                            "blue": 0.82, "alpha": 1,
                                        },
                                        "onClick": {
                                            "action": {
                                                "function": "edit_draft",
                                                "parameters": [
                                                    {"key": "draft_id", "value": draft_id_str},
                                                ],
                                            }
                                        },
                                    },
                                    {
                                        "text": "Reject",
                                        "color": {
                                            "red": 0.83, "green": 0.18,
                                            "blue": 0.18, "alpha": 1,
                                        },
                                        "onClick": {
                                            "action": {
                                                "function": "reject_draft",
                                                "parameters": [
                                                    {"key": "draft_id", "value": draft_id_str},
                                                ],
                                            }
                                        },
                                    },
                                ]
                            }
                        }
                    ],
                },
            ],
        },
    }


def build_alert_card(
    title: str,
    body: str,
    source: str,
    priority: str,
    event_id: str = "",
) -> dict:
    """Build a Chat Card for an alert notification."""
    return {
        "cardId": f"alert-{event_id[:8]}",
        "card": {
            "header": {
                "title": title,
                "subtitle": f"{source} | {priority}",
                "imageUrl": "https://fonts.gstatic.com/s/i/short-term/release/googlesymbols/warning/default/48px.svg",
                "imageType": "CIRCLE",
            },
            "sections": [
                {
                    "widgets": [
                        {
                            "textParagraph": {"text": body[:1000]}
                        },
                    ],
                },
                {
                    "widgets": [
                        {
                            "buttonList": {
                                "buttons": [
                                    {
                                        "text": "Acknowledge",
                                        "onClick": {
                                            "action": {
                                                "function": "ack_alert",
                                                "parameters": [
                                                    {"key": "event_id", "value": event_id},
                                                ],
                                            }
                                        },
                                    },
                                ]
                            }
                        }
                    ],
                },
            ],
        },
    }


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
