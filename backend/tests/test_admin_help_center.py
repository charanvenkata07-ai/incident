import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.help_service import HelpService, HELP_CATEGORIES, HELP_ARTICLES, ACTUAL_ADMIN_FEATURES
from app.core.security import create_access_token


from sqlalchemy import select
from app.core.database import async_session_maker
from app.models.user import User


async def get_auth_headers(role: str) -> dict:
    async with async_session_maker() as session:
        user = (await session.execute(select(User).where(User.role == role))).scalars().first()
        assert user is not None, f"User with role {role} must exist"
        token = create_access_token(data={"sub": str(user.id), "role": user.role})
        return {"Authorization": f"Bearer {token}"}




def test_help_categories_integrity():
    """Verify all 10 required Help categories are defined and populated."""
    categories = HelpService.get_categories()
    assert len(categories) == 10
    cat_ids = {c["id"] for c in categories}
    expected_ids = {
        "core_operations", "people_and_teams", "scheduling", "automation",
        "servicenow", "communication", "administration", "monitoring",
        "security", "troubleshooting"
    }
    assert cat_ids == expected_ids
    for c in categories:
        assert c["article_count"] > 0
        assert "name" in c
        assert "description" in c


def test_help_articles_structure_and_completeness():
    """Verify every Help article contains all required production sections."""
    articles = HelpService.get_articles()
    assert len(articles) >= len(ACTUAL_ADMIN_FEATURES)

    for a in articles:
        assert a.get("id"), "Missing id"
        assert a.get("slug"), f"Missing slug in {a.get('id')}"
        assert a.get("title"), f"Missing title in {a.get('slug')}"
        assert a.get("category_id"), f"Missing category_id in {a.get('slug')}"
        assert a.get("summary"), f"Missing summary in {a.get('slug')}"
        assert a.get("what_it_does"), f"Missing what_it_does in {a.get('slug')}"
        assert isinstance(a.get("how_it_works"), list) and len(a["how_it_works"]) > 0
        assert a.get("who_can_use_it"), f"Missing who_can_use_it in {a.get('slug')}"
        assert isinstance(a.get("important_rules"), list) and len(a["important_rules"]) > 0
        assert isinstance(a.get("troubleshooting"), list) and len(a["troubleshooting"]) > 0
        assert isinstance(a.get("faqs"), list) and len(a["faqs"]) > 0
        assert isinstance(a.get("summary_bullets"), list) and len(a["summary_bullets"]) > 0
        assert isinstance(a.get("keywords"), list) and len(a["keywords"]) > 0
        assert a.get("version"), f"Missing version in {a.get('slug')}"
        assert a.get("updated_at"), f"Missing updated_at in {a.get('slug')}"


def test_help_coverage_audit_100_percent():
    """Section 24: Test automated Help Coverage Audit returns 100% with 0 missing."""
    audit = HelpService.get_coverage_audit()
    assert audit["status"] == "COMPLETE"
    assert audit["help_coverage_percentage"] == 100.0
    assert audit["missing_features"] == []
    assert audit["documented_features"] == audit["total_admin_features"]
    assert audit["documented_features"] >= 40


def test_help_search_accuracy():
    """Verify high-precision search matches expected articles for prompt queries."""
    # Test "duplicate assignment"
    res1 = HelpService.search("duplicate assignment")
    assert res1["total_count"] > 0
    slugs1 = [item["slug"] for item in res1["results"]]
    assert any("duplicate" in s or "automatic" in s or "rotation" in s for s in slugs1)

    # Test "10 employees"
    res2 = HelpService.search("10 employees")
    assert res2["total_count"] > 0
    slugs2 = [item["slug"] for item in res2["results"]]
    assert "employee-management" in slugs2 or "team-management" in slugs2

    # Test "ServiceNow not connecting"
    res3 = HelpService.search("ServiceNow not connecting")
    assert res3["total_count"] > 0
    slugs3 = [item["slug"] for item in res3["results"]]
    assert any("servicenow" in s for s in slugs3)

    # Test "shift rotation"
    res4 = HelpService.search("shift rotation")
    assert res4["total_count"] > 0
    slugs4 = [item["slug"] for item in res4["results"]]
    assert any("shift" in s or "rotation" in s for s in slugs4)

    # Test "Sunday holiday"
    res5 = HelpService.search("Sunday holiday")
    assert res5["total_count"] > 0
    slugs5 = [item["slug"] for item in res5["results"]]
    assert any("sunday" in s or "working-days" in s for s in slugs5)


def test_help_summarize():
    """Verify summarize endpoint generates crisp bullets."""
    summary = HelpService.summarize_article("automatic-assignment-workflow")
    assert "bullets" in summary
    assert len(summary["bullets"]) > 0
    assert summary["title"] == "Automatic Assignment Engine"
    assert "important_rules" in summary


def test_contextual_help():
    """Verify contextual help lookup for inline popovers."""
    ctx = HelpService.get_contextual_help("shifts")
    assert ctx is not None
    assert "hint" in ctx
    assert "important_rules" in ctx
    assert ctx["slug"] == "shifts-and-scheduling"


@pytest.mark.asyncio
async def test_admin_help_api_endpoints():
    """Test full suite of REST endpoints under /api/admin/help."""
    admin_headers = await get_auth_headers("ADMIN")
    employee_headers = await get_auth_headers("EMPLOYEE")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Categories
        cat_res = await ac.get("/api/admin/help/categories", headers=admin_headers)
        assert cat_res.status_code == 200
        assert len(cat_res.json()) == 10

        # Articles list
        art_res = await ac.get("/api/admin/help/articles", headers=admin_headers)
        assert art_res.status_code == 200
        assert len(art_res.json()) >= 40

        # Filter by category
        sched_res = await ac.get("/api/admin/help/articles?category_id=scheduling", headers=admin_headers)
        assert sched_res.status_code == 200
        for item in sched_res.json():
            assert item["category_id"] == "scheduling"

        # Single article
        single_res = await ac.get("/api/admin/help/articles/automatic-assignment-workflow", headers=admin_headers)
        assert single_res.status_code == 200
        body = single_res.json()
        assert body["title"] == "Automatic Assignment Engine"
        assert len(body["how_it_works"]) >= 5
        assert len(body["faqs"]) >= 1

        # Search endpoint
        search_res = await ac.get("/api/admin/help/search?q=duplicate+assignment", headers=admin_headers)
        assert search_res.status_code == 200
        assert search_res.json()["total_count"] > 0

        # What's New endpoint
        news_res = await ac.get("/api/admin/help/whats-new", headers=admin_headers)
        assert news_res.status_code == 200
        assert len(news_res.json()) >= 3

        # Coverage Audit endpoint
        audit_res = await ac.get("/api/admin/help/audit", headers=admin_headers)
        assert audit_res.status_code == 200
        audit_body = audit_res.json()
        assert audit_body["status"] == "COMPLETE"
        assert audit_body["help_coverage_percentage"] == 100.0

        # Contextual endpoint
        ctx_res = await ac.get("/api/admin/help/contextual/shifts", headers=admin_headers)
        assert ctx_res.status_code == 200
        assert "hint" in ctx_res.json()

        # Summarize endpoint
        sum_res = await ac.post("/api/admin/help/articles/shifts-and-scheduling/summarize", headers=admin_headers)
        assert sum_res.status_code == 200
        assert len(sum_res.json()["bullets"]) > 0

        # Non-admin access to admin help is forbidden (HTTP 403)
        emp_res = await ac.get("/api/admin/help/audit", headers=employee_headers)
        assert emp_res.status_code == 403


@pytest.mark.asyncio
async def test_global_search_includes_help_for_admin():
    """Verify global search returns Help category for Admins but not for Employees."""
    admin_headers = await get_auth_headers("ADMIN")
    employee_headers = await get_auth_headers("EMPLOYEE")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        admin_search = await ac.get("/api/search?q=shift+rotation", headers=admin_headers)
        assert admin_search.status_code == 200
        data = admin_search.json()
        assert "help" in data["categories"]
        assert len(data["categories"]["help"]) > 0
        help_hit = data["categories"]["help"][0]
        assert help_hit["type"] == "HELP"
        assert "/admin/help" in help_hit["url"]

        # Employees do not receive Help results in global search
        emp_search = await ac.get("/api/search?q=shift+rotation", headers=employee_headers)
        assert emp_search.status_code == 200
        emp_data = emp_search.json()
        assert len(emp_data["categories"].get("help", [])) == 0

