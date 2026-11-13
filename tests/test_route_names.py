"""Device names for routes sharing a hostname."""

from dataclasses import replace

import pytest

from custom_components.traefik.entity import router_display_name


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ("Host(`example.test`) && PathPrefix(`/photos`)", "example.test/photos"),
        ('Path("/ping") && Host(`example.test`)', "example.test/ping"),
        ("Host(`example.test`)", "example.test"),
        ("Host(`example.test`) && PathPrefix(`/`)", "example.test"),
        ("Host(`example.test`) || Path(`/ping`)", "example.test"),
        ("PathPrefix(`/photos`)", "example@file"),
    ],
)
def test_router_display_name(router, rule, expected):
    route = replace(router, rule=rule)
    assert router_display_name(route, route.name) == expected
