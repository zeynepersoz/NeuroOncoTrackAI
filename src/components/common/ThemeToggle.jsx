import { useCallback, useRef, useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import { clampNumber } from '../../utils/neuroUtils.js';

export default function ThemeToggle({ theme, setTheme }) {
  const dragRef = useRef({ active: false, pointerId: null, startX: 0, moved: false });
  const [dragThumbX, setDragThumbX] = useState(null);
  const isDragging = dragThumbX !== null;

  const getDragX = useCallback((clientX, target) => {
    const rect = target.getBoundingClientRect();
    return clampNumber(clientX - rect.left - 21, 0, 33);
  }, []);

  const setThemeFromPointer = useCallback(
    (clientX, target) => {
      const rect = target.getBoundingClientRect();
      setTheme(clientX - rect.left >= rect.width / 2 ? 'dark' : 'light');
    },
    [setTheme],
  );

  const handlePointerDown = (event) => {
    if (event.button !== 0) return;
    dragRef.current = { active: true, pointerId: event.pointerId, startX: event.clientX, moved: false };
    setDragThumbX(theme === 'dark' ? 33 : 0);
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };

  const handlePointerMove = (event) => {
    const drag = dragRef.current;
    if (!drag.active) return;
    if (Math.abs(event.clientX - drag.startX) > 3) {
      drag.moved = true;
      event.preventDefault();
      setDragThumbX(getDragX(event.clientX, event.currentTarget));
      setThemeFromPointer(event.clientX, event.currentTarget);
    }
  };

  const finishPointerDrag = (event) => {
    const drag = dragRef.current;
    if (!drag.active) return;
    event.currentTarget.releasePointerCapture?.(drag.pointerId);
    dragRef.current = { active: false, pointerId: null, startX: 0, moved: false };
    setDragThumbX(null);

    if (drag.moved) {
      setThemeFromPointer(event.clientX, event.currentTarget);
      return;
    }

    setTheme((current) => (current === 'dark' ? 'light' : 'dark'));
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      setTheme((current) => (current === 'dark' ? 'light' : 'dark'));
    }
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      setTheme('light');
    }
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      setTheme('dark');
    }
  };

  return (
    <button
      className={`theme-toggle ${theme === 'dark' ? 'is-dark' : 'is-light'} ${isDragging ? 'is-dragging' : ''}`}
      type="button"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={finishPointerDrag}
      onPointerCancel={finishPointerDrag}
      onKeyDown={handleKeyDown}
      style={isDragging ? { '--theme-thumb-x': `${dragThumbX}px` } : undefined}
      aria-pressed={theme === 'dark'}
      aria-label={theme === 'dark' ? 'Açık temaya geç' : 'Koyu temaya geç'}
      title={theme === 'dark' ? 'Açık tema' : 'Koyu tema'}
    >
      <span className="theme-toggle-thumb" aria-hidden="true" />
      <span className="theme-toggle-icon sun" aria-hidden="true">
        <Sun size={15} />
      </span>
      <span className="theme-toggle-icon moon" aria-hidden="true">
        <Moon size={15} />
      </span>
    </button>
  );
}
