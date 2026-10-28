# Folava MCP site direction

A quiet, useful front door to a personal study tool. The homepage's main job is
to let someone hand setup to their agent. A copyable prompt and a plain guide
link come before the manual commands and fictional coursework example.

## Visual language

White #ffffff, soft paper #f5f5f5, graphite #242426, secondary ink #66666b and
rule #dedee2 form the light palette. Dark uses paper #18181b, panel #232326,
ink #eeeeef, secondary ink #b1b1b7 and rule #414147. Actions, selection, focus and
status messages use corresponding neutral tokens. Color does not carry meaning
alone. Avoid gradients, tinted feature grids and large offset card shadows.

Type remains a locally available humanist sans (Aptos/Segoe UI), with a generous
heading scale and readable body measure. Monospace is reserved for commands and
API examples. The original overlapping-note mark is a small supporting element;
the project name stays readable beside it. No Folava GUI assets are used.

The round, lightly translucent navigation is the main expressive detail. Its
blur sits over a sufficiently opaque surface; a solid fallback keeps text
readable when transparency is unavailable. Other sections use open space,
modest corner radii and quiet rules. The layout stays left-aligned, with the
actual setup note opposite the introduction and manual setup below.

## Behavior

System/Light/Dark is a native labelled selector on every page. System follows
OS changes; explicit choices persist locally across routes. A local initializer
applies the theme before styles load. Blocked storage permits a page-local
choice, and the no-JavaScript reading surface follows the OS.

Copy controls keep the setup prompt, link and commands available with a manual
selection fallback. The agent guide starts with a demo, preserves existing host
configuration and keeps authentication private. Coursework examples are fictional;
the website never connects to a student account.

Motion responds to actions or gives the setup note one finite, subtle arrival.
No looping motion, scroll reveals or decorative stagger. Reduced-motion
preferences disable authored animation and transitions. Clear keyboard focus,
contrast and responsive reading order are release requirements.
