# Moepet development notes

## Reference project

For future Moepet development, use the local MeaPet project at
`G:\pet\mea-pet-public` (currently branch
`fix/issue-35-provider-autodetection`) as the primary implementation and
product-design reference when it is relevant.

- Adopt its ideas and patterns selectively; do not copy its implementation
  verbatim or force Moepet to match it feature-for-feature.
- For configuration and settings UX in particular, inspect its configuration
  wizard/pages first and adapt the useful interaction and information-layout
  ideas to Moepet's PySide6 architecture and existing conventions.
- Preserve Moepet's own product direction, dependencies, naming, and visual
  identity unless a task explicitly requests alignment.
