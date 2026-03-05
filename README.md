# TODO App

A modern, type-safe TODO web application built with React 19, TypeScript, Vite 7, and Tailwind CSS 4.

## Tech Stack

- **React 19** - Latest React with improved performance and features
- **TypeScript** - Type-safe development
- **Vite 7** - Fast build tool and dev server
- **Tailwind CSS 4** - Utility-first CSS framework
- **ESLint** - Code linting and quality

## Getting Started

### Install Dependencies

```bash
npm install
```

### Development Server

```bash
npm run dev
```

The dev server will start at `http://0.0.0.0:3000` (accessible from host at container IP).

### Build for Production

```bash
npm run build
```

### Lint Code

```bash
npm run lint
```

## Project Structure

```
/
├── public/          # Static assets
├── src/             # Application source code
│   ├── main.tsx     # Application entry point
│   ├── App.tsx      # Root component
│   └── index.css    # Global styles with Tailwind imports
├── index.html       # HTML entry point
├── vite.config.ts   # Vite configuration
├── tsconfig.json    # TypeScript configuration
└── package.json     # Project dependencies and scripts
```

## Features (Coming Soon)

- Create, read, update, and delete TODOs
- Filter by all/active/completed
- Mark TODOs as complete/incomplete
- Clear completed TODOs
- Persistent storage with localStorage
- Responsive design
