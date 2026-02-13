# NOTE: The architecture of this solution utilizes the FastAPI framework to create a production-ready API. It includes type hints for better code readability and maintainability. The API will have a single endpoint to demonstrate the logic, but it can be extended to multiple endpoints as needed. The use of Pydantic for data validation ensures that the API is robust and handles invalid data gracefully.

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List

app = FastAPI()

class Item(BaseModel):
    """Data model for items"""
    id: int
    name: str
    price: float

# Define a router for items
item_router = FastAPI()

# Utility function to get items
def get_items() -> List[Item]:
    """Return a list of items"""
    # Placeholder data, replace with database query
    items = [
        Item(id=1, name="Item 1", price=9.99),
        Item(id=2, name="Item 2", price=19.99),
    ]
    return items

# Utility function to get item by id
def get_item(item_id: int) -> Item:
    """Return an item by id"""
    # Placeholder data, replace with database query
    items = [
        Item(id=1, name="Item 1", price=9.99),
        Item(id=2, name="Item 2", price=19.99),
    ]
    for item in items:
        if item.id == item_id:
            return item
    raise HTTPException(status_code=404, detail="Item not found")

# Item router endpoint to get all items
@item_router.get("/items/")
async def read_items():
    """Get all items"""
    return get_items()

# Item router endpoint to get item by id
@item_router.get("/items/{item_id}")
async def read_item(item_id: int):
    """Get item by id"""
    return get_item(item_id)

# Include the item router in the main application
app.include_router(item_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```