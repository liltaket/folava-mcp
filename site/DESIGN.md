# Folava MCP site direction

A quiet, useful front door to a personal study tool. The homepage's main job is
to let someone hand setup to their agent. A short installation row and a copy
icon come before the manual commands and fictional coursework example. The icon
copies the complete agent instructions; a native disclosure shows that text on
request and opens automatically if manual copying is needed.

The page should read as made by a person. It shows real demo output instead of
a mock conversation, has a short signed note from the maintainer and states its
limits plainly. Avoid template chrome: status pills, icon-and-fact rows, rows of
identical feature cards, info boxes with icons and steps repeated in two places.

## Visual language

White #ffffff, soft paper #f5f5f5, graphite #242426, secondary ink #66666b and
rule #dedee2 form the light palette. Dark uses paper #18181b, panel #232326,
ink #eeeeef, secondary ink #b1b1b7 and rule #414147. Actions, selection, focus and
status messages use corresponding neutral tokens. Color does not carry meaning
alone. A muted lilac #a38aca is the pencil: the hero underline, hand-drawn
circles and arrows, the selected example tab and a tint in the main action.
Handwritten text uses its darker ink #5b4880 for contrast. Avoid gradients,
tinted feature grids and large offset card shadows. The setup card is the only
raised box; the demo transcript sits on a flat paper panel.

Type is Schibsted Grotesk, self-hosted as a variable Latin WOFF2 in
`site/assets/fonts/`. Pencil notes, step numbers and the signature use Caveat,
also self-hosted. Both are under the SIL Open Font License, with their licence
files beside them, so pages make no font requests to third parties.
Aptos/Segoe UI remain the fallback.
Headings use weight 650–680 with tight tracking and a generous scale; body text
keeps a readable measure. Monospace is reserved for commands and API examples. The original overlapping-note mark is a small supporting element;
the project name stays readable beside it. No Folava GUI assets are used.

The round, lightly translucent navigation is the main expressive detail. Its
blur sits over a sufficiently opaque surface; a solid fallback keeps text
readable when transparency is unavailable. Desktop links and controls share a
compact capsule; search and its shortcut have no extra outline at rest.
Other sections use open space,
modest corner radii and quiet rules, with a varied rhythm instead of the same
two-column split everywhere. The hero keeps the setup card opposite the
introduction and ends with one plain sentence about the preview status. The
demo section runs full width: three question tabs above a trimmed transcript of
real `folava-mcp serve --demo` responses, with pencil circles on the key values
and handwritten notes in the margin (below the transcript on narrow screens).
The maintainer's note is a narrow, offset reading column signed by hand.
Terminal setup is the one tinted band and the only numbered sequence. What it
can and can't do is three short paragraphs with bold lead-ins, followed by a
small preview note above the footer.

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
icon and accessible action name show the destination theme. On click the icons
rotate past each other and the new theme grows out of the button as a circle
(a view transition); the choice is saved before the animation starts. It follows OS changes
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
The rounded dialog opens with five compact suggestions. Excerpts appear after
typing, limited to one visible line, and a search shows up to eight results.

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
the setup note keeps its subtle arrival. On wide screens the same sequence then
writes "start here" in the setup card and draws an arrow to the copy button.
Further pencil marks draw once when they first come into view, or again when an
example tab is selected: circles first, then the notes. The signature writes
itself the same way. No looping motion and no fades on ordinary sections.
Reduced-motion and script-free views show every mark complete and static.
In-page links scroll smoothly. When the setup card is already on screen, Agent
setup does not scroll: it focuses the card, which grows with a lilac ring while
its copy row glows and "start here" is written again. The highlight stays until
the visitor clicks outside the card, presses Escape or tabs away. Otherwise it
scrolls first and then highlights. Reduced motion swaps all of this for an
instant change and a static outline on the copy row. Clear keyboard focus, contrast and responsive
reading order are release requirements. The bookmark and paper-plane studies were
discarded after the pencil direction was selected.
