/**
 * Vitest setup file for React Testing Library
 * 
 * Configures the testing environment and adds custom matchers.
 */
import '@testing-library/jest-dom'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Cleanup after each test
afterEach(() => {
  cleanup()
})
