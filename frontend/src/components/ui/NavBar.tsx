import { Link, useLocation } from 'react-router-dom'
import { Marquee } from './Marquee'

export function NavBar() {
  const location = useLocation()
  const isVerify = location.pathname.startsWith('/verify')
  const isObs = location.pathname.startsWith('/observability')

  return (
    <div className="-mx-4 mb-10 animate-fade-in sm:mx-0">
      <div className="flex flex-wrap items-center justify-between gap-4 px-4 pb-4 sm:px-0">
        <Link to="/" className="flex items-center gap-2.5">
          <span className="relative flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-500 opacity-75" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-brand-500" />
          </span>
          <span className="font-display text-2xl uppercase tracking-wide text-neutral-50">
            Live <span className="bg-brand-500 px-1.5 text-black">Cutter</span>
          </span>
        </Link>
        <div className="flex border-2 border-neutral-700 font-display text-lg uppercase tracking-wide">
          <Link
            to="/"
            className={`px-4 py-1.5 transition ${
              !isVerify && !isObs ? 'bg-brand-500 text-black' : 'text-neutral-400 hover:text-neutral-100'
            }`}
          >
            Sessions
          </Link>
          <Link
            to="/verify"
            className={`border-l-2 border-neutral-700 px-4 py-1.5 transition ${
              isVerify ? 'bg-brand-500 text-black' : 'text-neutral-400 hover:text-neutral-100'
            }`}
          >
            Verifier
          </Link>
          <Link
            to="/observability"
            id="nav-observability"
            className={`border-l-2 border-neutral-700 px-4 py-1.5 transition ${
              isObs ? 'bg-brand-500 text-black' : 'text-neutral-400 hover:text-neutral-100'
            }`}
          >
            Observatory
          </Link>
        </div>
      </div>
      <Marquee text="CAPTURE THE STORY • VERIFY THE CLAIM • CUT THE CLIP • EXPOSE THE FAKE •" />
    </div>
  )
}
