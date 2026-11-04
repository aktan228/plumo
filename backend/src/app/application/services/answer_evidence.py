"""Version fingerprints captured from the exact business and knowledge used for an answer."""
from hashlib import sha256


def answer_evidence(business, knowledge=()):
    publication = (business.profile or {}).get("onboarding_publication") or {}
    return {"publication_version": publication.get("draft_version"), "source_versions": [
        {"id": str(hit.item.id), "title": hit.item.title,
         "updated_at": hit.item.updated_at.isoformat(),
         "content_sha256": sha256(hit.item.content.encode("utf-8")).hexdigest()}
        for hit in knowledge
    ]}
