---
name: Terra Insight
colors:
  surface: '#fbf9f4'
  surface-dim: '#dbdad5'
  surface-bright: '#fbf9f4'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f5f3ee'
  surface-container: '#f0eee9'
  surface-container-high: '#eae8e3'
  surface-container-highest: '#e4e2dd'
  on-surface: '#1b1c19'
  on-surface-variant: '#54433e'
  inverse-surface: '#30312e'
  inverse-on-surface: '#f2f1ec'
  outline: '#87736d'
  outline-variant: '#dac1ba'
  surface-tint: '#954830'
  primary: '#91452d'
  on-primary: '#ffffff'
  primary-container: '#af5d43'
  on-primary-container: '#fffaf9'
  inverse-primary: '#ffb59e'
  secondary: '#865220'
  on-secondary: '#ffffff'
  secondary-container: '#feb87c'
  on-secondary-container: '#784714'
  tertiary: '#625a4e'
  on-tertiary: '#ffffff'
  tertiary-container: '#7b7366'
  on-tertiary-container: '#fffbfa'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#ffdbd0'
  primary-fixed-dim: '#ffb59e'
  on-primary-fixed: '#3a0b00'
  on-primary-fixed-variant: '#77321b'
  secondary-fixed: '#ffdcc1'
  secondary-fixed-dim: '#feb87c'
  on-secondary-fixed: '#2e1500'
  on-secondary-fixed-variant: '#6a3b08'
  tertiary-fixed: '#ece1d1'
  tertiary-fixed-dim: '#d0c5b6'
  on-tertiary-fixed: '#201b11'
  on-tertiary-fixed-variant: '#4d463a'
  background: '#fbf9f4'
  on-background: '#1b1c19'
  surface-variant: '#e4e2dd'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '600'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '500'
    lineHeight: 32px
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-caps:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: 0.05em
  data-tabular:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 8px
  container-max: 1440px
  gutter: 24px
  margin-mobile: 16px
  margin-desktop: 48px
  section-gap: 64px
---

## Brand & Style

The design system is centered on the concept of "Grounded Intelligence." It balances the clinical precision required for environmental data analysis with an organic, tactile aesthetic that reflects the subject matter: the Earth’s biodiversity. 

The target audience consists of ESG analysts, sustainability officers, and institutional investors who require professional, high-density information presented without visual clutter. The style is **Minimalist with Organic Textures**, utilizing expansive whitespace to reduce cognitive load. Subtle, hand-painted watercolor textures are applied to large background surfaces or data clusters to provide a humanistic, softening contrast to the rigid data visualizations. The emotional response is one of calm authority, transparency, and ecological stewardship.

## Colors
The palette is derived from natural strata and raw pigments.
- **Primary (Terra Cotta):** Used for primary actions, active states, and high-impact data points.
- **Secondary (Ochre):** Used for secondary highlights, warning states, and mid-level risk categories.
- **Tertiary (Clay/Mud):** A muted, grounding tone for iconography and secondary typography.
- **Neutral (Parchment):** The base background color, replacing pure white to reduce eye strain and reinforce the organic feel.

Background surfaces utilize a very faint, non-tiling watercolor grain (`#F2EEE6`) to provide depth without distracting from the data.

## Typography
Inter is chosen for its exceptional legibility in data-heavy environments and its modern, neutral tone. 
- **Hierarchy:** We use tight letter spacing for large headlines to create a sophisticated, editorial feel. 
- **Data Clarity:** For tables and risk assessments, `data-tabular` utilizes tabular num features to ensure numerical values align vertically for easy comparison.
- **Labels:** Small caps are used for metadata labels to provide a distinct visual rhythm between titles and descriptions.

## Layout & Spacing
The design system employs a **Fixed Grid** on desktop (12 columns) and a **Fluid Grid** on mobile (4 columns). 
- **Whitespace:** Emphasize generous margins (`48px` on desktop) to allow the "organic" elements room to breathe.
- **Rhythm:** All spacing is a multiple of `8px`. Component internal padding should favor `16px` or `24px` to maintain a professional, airy feel.
- **Adaptive Reflow:** On tablet, the 12-column grid transitions to 8 columns, with sidebar navigation collapsing into a bottom bar or hamburger menu to prioritize the workspace.

## Elevation & Depth
To maintain a minimalist aesthetic, this design system avoids heavy shadows. Instead, it uses **Tonal Layers** and **Subtle Outlines**:
- **Level 0 (Canvas):** The base neutral color with a faint watercolor texture.
- **Level 1 (Cards):** Solid white or slightly lighter parchment background with a `1px` stroke in `#E8E0D5`. No shadow.
- **Level 2 (Modals/Popovers):** A very soft, ultra-diffused shadow (`0px 12px 32px rgba(115, 107, 94, 0.08)`) to suggest a slight lift without appearing heavy.
- **Glassmorphism:** Used sparingly for sticky headers or sidebars, featuring a `backdrop-filter: blur(12px)` and `80%` opacity of the base neutral color.

## Shapes
The shape language is **Soft**. 
A `0.25rem` (4px) base radius is used for input fields and small buttons to maintain a "professional" edge. Larger containers, such as data cards or status banners, use `0.5rem` (8px). This slight rounding removes the harshness of a technical dashboard while remaining structured enough for financial-grade reporting.

## Components
- **Primary Buttons:** Solid `Primary Terra Cotta` with white text. High-contrast, no gradients.
- **Risk Indicators:** Use a "Pill" shape with a background tint and dark text (e.g., Critical Risk = Dark Red text on Pale Red background).
- **Data Visualization:** Charts should use the Earthy palette. Avoid neon colors. Lines should be slightly softened/curved rather than jagged.
- **Input Fields:** Minimalist design with only a bottom border or a very light `1px` clay-colored stroke. Use `Inter Body-SM` for placeholder text.
- **Cards:** White backgrounds, subtle clay borders, and generous `24px` internal padding.
- **Impact Assessment Sliders:** Use a custom-styled track in `Clay` with a `Primary` thumb to represent dependency levels.
- **Watercolor Background Tiers:** For dashboard headers, use a CSS mask or background-image of a light watercolor wash in `Ochre` or `Clay` to create a distinctive, premium entrance point.