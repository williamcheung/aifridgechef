{%- for item in items %}
- **{{ item.food }}**{% if item.brand %} ({{ item.brand }}){% endif %} x{{ item.quantity }}
{%- endfor %}
