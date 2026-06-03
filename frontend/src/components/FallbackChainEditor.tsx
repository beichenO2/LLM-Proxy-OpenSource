import clsx from "clsx";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { linkDangerClass } from "../lib/styles";

interface FallbackChainEditorProps {
  chain: string[];
  onChange: (chain: string[]) => void;
  onRemove: (index: number) => void;
}

function SortableItem({
  id,
  name,
  onRemove,
}: {
  id: string;
  name: string;
  onRemove: () => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={clsx(
        "flex items-center gap-2 px-3 py-2 bg-neutral-50 border border-neutral-200 rounded-md",
        isDragging && "opacity-50 shadow-md"
      )}
    >
      <span
        {...attributes}
        {...listeners}
        className="cursor-grab text-neutral-400 hover:text-neutral-600"
      >
        ☰
      </span>
      <span className="flex-1 font-mono text-sm text-neutral-800">{name}</span>
      <button
        type="button"
        onClick={onRemove}
        className={clsx(linkDangerClass, "text-xs")}
      >
        Remove
      </button>
    </div>
  );
}

export default function FallbackChainEditor({
  chain,
  onChange,
  onRemove,
}: FallbackChainEditorProps) {
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;

    if (over && active.id !== over.id) {
      const oldIndex = chain.indexOf(active.id as string);
      const newIndex = chain.indexOf(over.id as string);
      onChange(arrayMove(chain, oldIndex, newIndex));
    }
  };

  if (chain.length === 0) {
    return (
      <p className="text-sm text-neutral-500 italic">
        No fallback bindings configured.
      </p>
    );
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={handleDragEnd}
    >
      <SortableContext items={chain} strategy={verticalListSortingStrategy}>
        <div className="space-y-2">
          {chain.map((name, index) => (
            <SortableItem
              key={name}
              id={name}
              name={name}
              onRemove={() => onRemove(index)}
            />
          ))}
        </div>
      </SortableContext>
    </DndContext>
  );
}