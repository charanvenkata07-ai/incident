from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field
from app.core.security import get_current_user, require_role
from app.models.user import User
from app.services.help_service import HelpService

router = APIRouter()


class CommonProblemSchema(BaseModel):
    problem: str
    cause: Optional[str] = None
    resolution: str


class FAQItemSchema(BaseModel):
    question: str
    answer: str


class HelpArticleDetailSchema(BaseModel):
    id: str
    slug: str
    title: str
    summary: str
    category_id: str
    category_name: str
    what_it_does: str
    how_it_works: Union[List[str], str]
    who_can_use_it: List[str]
    who_can_use_it_description: Optional[str] = None
    status: Optional[str] = "DOCUMENTED"
    version: Optional[str] = "2.4.0"
    updated_at: Optional[str] = None
    important_rules: List[str] = []
    common_problems: List[CommonProblemSchema] = []
    troubleshooting_steps: List[str] = []
    faqs: List[FAQItemSchema] = []
    related_features: List[str] = []
    tags: List[str] = []

    model_config = {"extra": "ignore"}


@router.get("/categories", response_model=List[Dict[str, Any]])
async def get_help_categories(
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR"]))
):
    """
    Returns all Admin Help categories with metadata, icons, and article counts.
    """
    return HelpService.get_categories()


@router.get("/articles", response_model=List[Dict[str, Any]])
async def get_help_articles(
    category_id: Optional[str] = Query(None, description="Filter by category ID"),
    status: Optional[str] = Query(None, description="Filter by status (DOCUMENTED, NEW, UPDATED)"),
    q: Optional[str] = Query(None, description="Filter by keyword query"),
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR"]))
):
    """
    Returns all documented Admin features matching optional category, status, or search query.
    """
    return HelpService.get_articles(category_id=category_id, status=status, query=q)


@router.get("/articles/{slug}", response_model=HelpArticleDetailSchema)
async def get_help_article(
    slug: str,
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR"]))
):
    """
    Returns the comprehensive Help article with full structured sections:
    What It Does, How It Works, Permissions, Important Rules, Troubleshooting, and FAQs.
    """
    article = HelpService.get_article(slug)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Help documentation article '{slug}' not found"
        )
    return article


@router.get("/search", response_model=Dict[str, Any])
async def search_help(
    q: str = Query(..., description="Search query string"),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR"]))
):
    """
    High-precision Help search matching titles, summaries, keywords, troubleshooting causes, and content.
    """
    return HelpService.search(q, limit=limit)


@router.get("/whats-new", response_model=List[Dict[str, Any]])
async def get_whats_new(
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR"]))
):
    """
    Returns recent features and changelog updates with links to documentation.
    """
    return HelpService.get_whats_new()


@router.get("/audit", response_model=Dict[str, Any])
async def get_coverage_audit(
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR"]))
):
    """
    Section 24: Automatic Help Coverage Audit.
    Compares ACTUAL ADMIN FEATURES against DOCUMENTED HELP ARTICLES.
    Verifies 100% coverage and flags any missing features.
    """
    return HelpService.get_coverage_audit()


@router.get("/contextual/{feature_key}", response_model=Dict[str, Any])
async def get_contextual_help(
    feature_key: str,
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR"]))
):
    """
    Returns concise contextual help snippet for inline popovers beside complicated controls.
    """
    help_data = HelpService.get_contextual_help(feature_key)
    if not help_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contextual help for '{feature_key}' not found"
        )
    return help_data


@router.post("/articles/{slug}/summarize", response_model=Dict[str, Any])
async def summarize_help_article(
    slug: str,
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR"]))
):
    """
    Generates an immediate, crisp bullet-point summary of the requested feature.
    """
    summary = HelpService.summarize_article(slug)
    if "error" in summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=summary["error"]
        )
    return summary
