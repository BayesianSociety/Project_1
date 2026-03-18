# Project Description

## Project Summary

Build a browser-based educational coding game called `Pet Vet Coding Puzzles`.

The product is a beginner-friendly puzzle game in which the player acts as an assistant vet and solves programming puzzles by assembling visual code blocks. The game must teach sequencing, loops, and conditionals through puzzle-based progression. It must also include SQLite-backed telemetry that records all gameplay and UI events, including movement steps.

The experience must be original in assets and characters. It may take thematic inspiration from a pet-vet learning activity, but it must not use proprietary brand characters or logos.

## Scope

This run is expected to produce a complete working application with:

- a frontend game UI
- a backend that persists telemetry to SQLite
- 17 playable puzzles
- a block-based workspace with an `On Start` root
- execution, reset, and failure feedback flows
- analytics pages that read from SQLite

In scope:

- puzzle progression
- drag-and-drop block coding workflow
- puzzle execution and animation
- telemetry capture for gameplay and UI activity
- local analytics and replay views

Out of scope unless needed for implementation:

- use of proprietary third-party characters or branding
- native apps
- multiplayer
- cloud hosting requirements

## Functional Requirements

### Core Game Loop

The application must provide:

- a landing screen with a start action and optional how-to-play guidance
- a puzzle map or level-select view with 17 puzzles and lock/unlock progression
- a puzzle screen that loads one scene at a time
- a workspace where the player assembles a program and runs it
- success and failure handling for each run

Each puzzle must include:

- a scene background
- at least one pet and optional mentor presence
- objects and target locations as required by the puzzle
- a goal statement
- a limited set of available blocks for that puzzle
- a code area with a fixed `On Start` root block

Success requires:

- the required objective is completed
- the program finishes
- the puzzle can be marked complete and progression can advance

### Workspace And Interaction Model

The workspace must include:

- a command library on the left
- an active code area on the right
- visually connected blocks under a fixed `On Start` root
- a warning when blocks are disconnected and therefore will not execute

The command library must support categories for:

- movement
- actions
- control / loops
- logic / conditionals
- sensing

The run controls must include:

- `Play`
- `Reset`
- a speed toggle

A step-through control is optional.

When the user presses `Play`, the program must execute and animate the scene. During execution, the workspace should hide or minimize enough for the animation to be visible.

### Failure Feedback

Incorrect solutions must show:

- an `Oops!` message
- a helpful hint tied to the failure reason

Failure reasons should cover at least:

- target not reached
- wrong item used
- wrong order
- obstacle collision
- required condition not handled

### Concepts And Puzzle Progression

The game must teach these concepts:

- sequencing
- loops
- conditionals

The 17 puzzles must increase in complexity:

- puzzles 1 to 5 focus on sequencing basics
- puzzles 6 to 10 introduce loops
- puzzles 11 to 17 introduce conditionals and mixed logic

### Puzzle Data

Puzzles must be data-driven so additional puzzles can be added without changing core game logic.

Each puzzle definition must include enough data to represent:

- id
- title
- story text
- goal text
- scene identifier
- grid definition
- entities
- available blocks
- constraints
- success criteria
- hint rules

### Execution Engine

The game runtime must:

- compile the connected block sequence or graph under `On Start` into executable instructions
- execute instructions deterministically
- animate movement step by step
- wait for or sequence animation completion appropriately
- evaluate conditions from world state
- prevent infinite loops with a safety cap

Movement and world logic must support:

- tile-based movement
- facing direction
- optional turning actions
- collision handling
- item pickup
- treatment actions
- stateful symptoms such as itchy, sniffles, or injured

### Code View

The game must provide a `Show Code` toggle that displays an equivalent text representation of the visual program. Read-only text output is acceptable.

## Telemetry And Data Requirements

Telemetry is mandatory. The system must record all gameplay and UI events that occur in the game, including movement.

The backend must own a SQLite database. The frontend must send event data to the backend through HTTP endpoints. High-volume UI events may be buffered or debounced, but movement steps and block execution steps must not be dropped.

The SQLite design must include tables for:

- `users`
- `sessions`
- `puzzles`
- `attempts`
- `events`
- `movements`
- `puzzle_progress`

The telemetry model must support recording:

- session lifecycle
- puzzle open and close events
- play and reset events
- block edits and reordering
- run start and end
- block execution start and finish
- every movement step
- turns
- collisions
- item pickups
- treatment actions
- hints shown
- puzzle completion
- run outcome including success or failure and failure reason
- code snapshot at play time

Analytics must include:

- a dashboard with overall aggregates
- puzzle detail views
- per-attempt history
- readable event stream inspection
- replay of movement paths from stored movement data

## Technical Constraints

Required technical direction from the source brief:

- frontend in TypeScript
- React or an equivalent frontend framework
- canvas-based or lightweight 2D rendering
- drag-and-drop block UI, either custom or Blockly with substantial styling
- backend in Node.js with TypeScript
- HTTP API for session, event, and analytics flows
- SQLite for persistence

The application must run in a modern browser and should require no downloads for end users beyond normal web access.

Accessibility requirements:

- keyboard navigation for major controls
- color contrast suitable for readability
- no essential information conveyed by color alone
- optional text-to-speech for goal text

## API And Data Expectations

The backend API must support endpoints for:

- starting a session
- ending a session
- batching event submission
- reading analytics data

The source brief explicitly names these endpoint shapes:

- `POST /api/session/start`
- `POST /api/session/end`
- `POST /api/events/batch`
- `GET /api/analytics/*`

## User Experience Requirements

The interface should be polished, consistent, and readable, with:

- a top bar showing title and puzzle progress
- a main scene area
- a workspace overlay or panel
- large primary controls
- clear visual grouping
- smooth interactions

The visual language should be friendly and professional rather than generic or placeholder-like.

## Repository And Artifact Expectations

This brief is the canonical input for a run of the repository’s multi-agent workflow.

The implementation plan must produce concrete relative file paths for all owned work and all required outputs. The final implementation must include:

- application source for the frontend
- application source for the backend
- puzzle data definitions
- SQLite schema or initialization logic
- analytics functionality
- any required configuration needed to run the application

The exact file layout is not fixed by this brief. The planner must choose concrete paths that fit the implemented stack and keep ownership boundaries unambiguous.

## Validation Requirements

The implementation must satisfy these acceptance criteria:

1. The application contains exactly 17 playable puzzles with clear progression.
2. Each puzzle has a left-side block library and right-side active code area under an `On Start` root.
3. `Play` executes the code and animates the scene.
4. Incorrect solutions show `Oops!` and a helpful hint.
5. SQLite is created automatically on first run.
6. A completed run persists an `attempts` row, `events` rows, and `movements` rows when movement occurs.
7. Analytics can replay a run from stored movement data.

Validation for the implementation should include:

- build checks for the chosen frontend and backend stack
- runtime checks that the app starts successfully
- verification that database initialization occurs automatically
- verification that telemetry rows are written for runs and movements
- verification that analytics can read stored run data

The exact shell commands are not fixed in this brief and should be chosen to match the actual implementation.

## Assumptions And Open Questions

Assumptions taken directly from the source brief:

- the target experience is a self-directed beginner learning game
- the game is browser-based
- the application includes both gameplay and local analytics capabilities
- original characters and assets will be used

Open questions not resolved by the source brief:

- exact package manager and project layout
- exact rendering library
- exact block editor implementation details
- exact authentication or access control model for analytics beyond local-only or protected access
