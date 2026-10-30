# Folava MCP site direction

A quiet, useful front door to a personal study tool. The homepage's main job is
to let someone hand setup to their agent. A short installation row and a copy
icon come before the manual commands and fictional coursework example. The icon
copies the complete agent instructions; a native disclosure shows that text on
request and opens automatically if manual copying is needed.

## Visual language

White #ffffff, soft paper #f5f5f5, graphite #242426, secondary ink #66666b and
rule #dedee2 form the light palette. Dark uses paper #18181b, panel #232326,
ink #eeeeef, secondary ink #b1b1b7 and rule #414147. Actions, selection, focus and
status messages use corresponding neutral tokens. Color does not carry meaning
alone. A muted lilac #a38aca is reserved for the hero's pencil mark and a small
tint in its main action. Avoid gradients, tinted feature grids and large offset
card shadows.

Type remains a locally available humanist sans (Aptos/Segoe UI), with a generous
heading scale and readable body measure. Monospace is reserved for commands and
API examples. The original overlapping-note mark is a small supporting element;
the project name stays readable beside it. No Folava GUI assets are used.

The round, lightly translucent navigation is the main expressive detail. Its
blur sits over a sufficiently opaque surface; a solid fallback keeps text
readable when transparency is unavailable. Other sections use open space,
modest corner radii and quiet rules. The layout stays left-aligned, with the
actual setup note opposite the introduction and manual setup below.

On phones, the hero becomes a narrow reading column with a fluid two-line
headline. Its spacing brings the copyable setup command closer to the introduction;
the setup note uses smaller type and padding while retaining 44px touch controls.
The pencil mark keeps the same proportion to Canvas as the heading scales.

The reference pages use the same type, surfaces and navigation. Guides have a
grouped reading rail, section links and previous/next pages. The API catalog has
its own resource rail, operation IDs and expandable request examples. The two
areas stay distinct in navigation and search results. On smaller screens the
rails and page contents collapse into native disclosures above the article.

## Copy

Use short, concrete headings and name the action a control performs. Let the
fictional course example show the use cases rather than repeating them in a
benefits section. Keep implementation details in the guides, with concise data
handling, access limits and development-preview status visible on the homepage.
Reviewed reads do not imply that Canvas leaves all remote state unchanged.

## Behavior

One unboxed sun/moon button switches between light and dark on every page. Its
icon and accessible action name show the destination theme. It follows OS changes
until the visitor makes a choice; that choice persists locally across routes.
A local initializer applies the theme before styles load. Blocked storage permits
a page-local choice, and the no-JavaScript reading surface follows the OS.
On mobile, the mark, search, theme and hamburger share one compact row. The
hamburger reveals the navigation links inside the same rounded surface. Escape,
link selection, outside clicks and leaving the header by keyboard close it;
Escape returns focus to the toggle. Link order follows the expanded layout.
Without JavaScript the navigation links remain available.

The search button and Cmd+K/Ctrl+K open one native modal on every page. Guide
headings and API operations share a versioned static index, with visible type
labels in the results. Keyboard selection, focus restoration, loading, empty and
retry states belong to the same flow. Queries remain in memory in the browser;
the only search request fetches the public index without query terms.

Copy controls share the same overlapping-square icon and 44px target across the
homepage, guides and API examples. Success briefly replaces the icon with a check;
screen readers receive an announcement without a visual toast. Blocked copying
selects the source and shows a small instruction beside it for manual copying.
The agent guide starts with a demo, preserves existing host
configuration and keeps authentication private. Coursework examples are fictional;
the website never connects to a student account.

The selected pencil study adds a small school reference without adding hero copy.
A solid, clearly defined pencil draws one curved lilac line beneath Canvas,
passing in front of the letters before moving aside and fading out. The heading
has no final period, leaving the completed line
clear of extra punctuation or a parked pencil. Motion runs once for 3.8 seconds;
the setup note keeps its subtle arrival. No looping motion, scroll reveals or
decorative stagger. Reduced-motion views retain a complete static mark; the
artwork also works without scripts. Clear keyboard focus, contrast and responsive
reading order are release requirements. The bookmark and paper-plane studies were
discarded after the pencil direction was selected.
