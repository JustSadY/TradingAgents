import React, { Component, ErrorInfo, ReactNode } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
  name?: string
}

interface State {
  hasError: boolean
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false
  }

  public static getDerivedStateFromError(_: Error): State {
    return { hasError: true }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error(`Uncaught error in ${this.props.name || 'Component'}:`, error, errorInfo)
  }

  public render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="p-8 rounded-3xl bg-slate-900 border border-rose-500/20 flex flex-col items-center justify-center text-center space-y-4 shadow-2xl">
          <div className="p-4 rounded-full bg-rose-500/10 text-rose-500">
            <AlertTriangle size={32} />
          </div>
          <div className="space-y-2">
            <h3 className="text-white font-display font-bold">Component Crash</h3>
            <p className="text-xs text-slate-500 max-w-xs leading-relaxed">
              Something went wrong while rendering this part of the application ({this.props.name}).
            </p>
          </div>
          <button 
            onClick={() => window.location.reload()}
            className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-white text-xs font-bold transition-all border border-white/[0.04]"
          >
            <RefreshCw size={14} /> Reload Page
          </button>
        </div>
      )
    }

    return this.children
  }
}
