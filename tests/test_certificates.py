from backend.app.api.certificates import certificate_company_name


def test_certificate_drops_spring_fulfillment_alias():
    assert certificate_company_name("틸리언 (스프링풀필먼트)") == "틸리언"
    assert certificate_company_name("틸리언(스프링풀필먼트)") == "틸리언"
    assert certificate_company_name("틸리언") == "틸리언"
