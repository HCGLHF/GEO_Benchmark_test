from scripts.cloud.create_industry import build_industry_record, create_industry


def test_build_industry_record_normalizes_slug_and_trims_metadata():
    record = build_industry_record(
        industry_id=" Dental ",
        display_name=" Dental Clinics ",
        region=" AU ",
        notes=" Australian dental services corpus ",
    )

    assert record == {
        "industry_id": "dental",
        "display_name": "Dental Clinics",
        "region": "AU",
        "notes": "Australian dental services corpus",
    }


def test_create_industry_dry_run_returns_record_without_cloud_dependencies():
    result = create_industry(
        industry_id=" Legal ",
        display_name="Legal Services",
        region="Global",
        notes="Legal vertical corpus.",
        execute=False,
    )

    assert result == {
        "status": "dry_run",
        "industry": {
            "industry_id": "legal",
            "display_name": "Legal Services",
            "region": "Global",
            "notes": "Legal vertical corpus.",
        },
    }
