/**
 * Tests for App component
 * 
 * Example component tests using Vitest and React Testing Library.
 */
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import App from './App'

describe('App', () => {
  it('renders without crashing', () => {
    render(<App />)
    expect(screen.getByText(/Vite \+ React/i)).toBeInTheDocument()
  })

  it('displays Vite and React logos', () => {
    render(<App />)
    
    const viteLogo = screen.getByAltText('Vite logo')
    const reactLogo = screen.getByAltText('React logo')
    
    expect(viteLogo).toBeInTheDocument()
    expect(reactLogo).toBeInTheDocument()
  })

  it('has a counter button with initial value of 0', () => {
    render(<App />)
    
    const button = screen.getByRole('button', { name: /count is 0/i })
    expect(button).toBeInTheDocument()
  })

  it('increments counter when button is clicked', () => {
    render(<App />)
    
    const button = screen.getByRole('button', { name: /count is 0/i })
    
    fireEvent.click(button)
    
    expect(screen.getByRole('button', { name: /count is 1/i })).toBeInTheDocument()
  })

  it('increments counter multiple times', () => {
    render(<App />)
    
    const button = screen.getByRole('button', { name: /count is 0/i })
    
    fireEvent.click(button)
    fireEvent.click(button)
    fireEvent.click(button)
    
    expect(screen.getByRole('button', { name: /count is 3/i })).toBeInTheDocument()
  })

  it('displays "read the docs" text', () => {
    render(<App />)
    
    expect(screen.getByText(/Click on the Vite and React logos to learn more/i))
      .toBeInTheDocument()
  })

  it('contains links to Vite and React documentation', () => {
    render(<App />)
    
    const viteLink = screen.getByRole('link', { name: /vite logo/i })
    const reactLink = screen.getByRole('link', { name: /react logo/i })
    
    expect(viteLink).toHaveAttribute('href', 'https://vite.dev')
    expect(reactLink).toHaveAttribute('href', 'https://react.dev')
  })

  it('links open in new tab', () => {
    render(<App />)
    
    const viteLink = screen.getByRole('link', { name: /vite logo/i })
    const reactLink = screen.getByRole('link', { name: /react logo/i })
    
    expect(viteLink).toHaveAttribute('target', '_blank')
    expect(reactLink).toHaveAttribute('target', '_blank')
  })
})
