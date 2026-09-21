import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import async_session_maker
from app.core.security import create_access_token
from app.models.user import User
from app.services.help_service import HelpService, HELP_CATEGORIES, HELP_ARTICLES
import uuid


@pytest.mark.asyncio
async def test_help_categories_complete():
    """Verify all categories are documented and have metadata."""
    categories = HelpService.get_categories()
    assert len(categories) == 10
    for cat in categories:
        assert cat["id"]
        assert cat["name"]
        assert cat["description"]
        assert cat["icon"]
        assert cat["article_count"] > 0


@pytest.mark.asyncio
async def test_help_articles_contract_all_43():
    """Verify all 43 articles satisfy strict contract invariants."""
    articles = HelpService.get_articles()
    assert len(articles) == 43

    valid_roles = {"ADMIN", "SUPERVISOR", "GROUP_LEADER", "EMPLOYEE"}

    for a in articles:
        # who_can_use_it MUST be list of strings
        assert isinstance(a["who_can_use_it"], list), f"{a['slug']}: who_can_use_it not a list"
        assert len(a["who_can_use_it"]) > 0, f"{a['slug']}: who_can_use_it is empty"
        for r in a["who_can_use_it"]:
            assert isinstance(r, str), f"{a['slug']}: role {r} is not str"
            assert r in valid_roles, f"{a['slug']}: unexpected role {r}"

        # who_can_use_it_description MUST be a non-empty string
        assert isinstance(a.get("who_can_use_it_description"), str), f"{a['slug']}: missing who_can_use_it_description"
        assert len(a["who_can_use_it_description"]) > 0

        # how_it_works MUST be string or list of strings
        assert isinstance(a["how_it_works"], (str, list)), f"{a['slug']}: how_it_works is not str or list"
        assert len(a["how_it_works"]) > 0

        # important_rules MUST be list of strings
        assert isinstance(a["important_rules"], list), f"{a['slug']}: important_rules is not list"
        for rule in a["important_rules"]:
            assert isinstance(rule, str)

        # common_problems MUST be list of dicts with problem, cause, resolution
        assert isinstance(a["common_problems"], list), f"{a['slug']}: common_problems is not list"
        for cp in a["common_problems"]:
            assert isinstance(cp, dict), f"{a['slug']}: cp {cp} is not dict"
            assert "problem" in cp and "resolution" in cp

        # troubleshooting_steps MUST be list of strings
        assert isinstance(a["troubleshooting_steps"], list), f"{a['slug']}: troubleshooting_steps not list"

        # faqs MUST be list of dicts with question and answer
        assert isinstance(a["faqs"], list), f"{a['slug']}: faqs not list"
        for f in a["faqs"]:
            assert isinstance(f, dict)
            assert "question" in f and "answer" in f


@pytest.mark.asyncio
async def test_help_coverage_audit():
    """Verify Section 24 coverage audit returns 100% COMPLETE coverage."""
    audit = HelpService.get_coverage_audit()
    assert audit["status"] == "COMPLETE"
    assert audit["help_coverage_percentage"] == 100.0
    assert len(audit["missing_features"]) == 0
    assert audit["documented_features"] == 43


@pytest.mark.asyncio
async def test_help_api_endpoints():
    """Verify Help API endpoints return 200 and strictly validated responses."""
    async with async_session_maker() as session:
        admin_user = User(
            id=uuid.uuid4(),
            email=f"help_admin_{uuid.uuid4().hex[:6]}@incidentflow.dev",
            hashed_password="pw",
            full_name="Help Admin",
            role="ADMIN",
            is_active=True
        )
        session.add(admin_user)
        await session.commit()

        token = create_access_token({"sub": str(admin_user.id), "role": admin_user.role})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Categories
        cat_resp = await client.get("/api/admin/help/categories", headers=headers)
        assert cat_resp.status_code == 200
        cats = cat_resp.json()
        assert len(cats) == 10

        # 2. Single Article with full contract
        art_resp = await client.get("/api/admin/help/articles/admin-dashboard", headers=headers)
        assert art_resp.status_code == 200
        art = art_resp.json()
        assert art["slug"] == "admin-dashboard"
        assert isinstance(art["who_can_use_it"], list)
        assert "ADMIN" in art["who_can_use_it"]
        assert isinstance(art["how_it_works"], (str, list))
        assert isinstance(art["common_problems"], list)

        # 3. Search
        search_resp = await client.get("/api/admin/help/search?q=assignment", headers=headers)
        assert search_resp.status_code == 200
        res = search_resp.json()
        assert res["total_count"] > 0

        # 4. Contextual Help
        ctx_resp = await client.get("/api/admin/help/contextual/admin_dashboard", headers=headers)
        assert ctx_resp.status_code == 200
        ctx = ctx_resp.json()
        assert ctx["title"] == "Admin Dashboard"

        # 404 for unknown article
        not_found = await client.get("/api/admin/help/articles/nonexistent-article-xyz", headers=headers)
        assert not_found.status_code == 404
